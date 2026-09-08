"""Visible source-frame codes for the owned 960x540/30 fps rehearsal adapter.

CRC detects damaged pixels; it is not an authentication mechanism.
"""
import binascii
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

MAGIC = b"\xc1\x01"
CELL, WIDTH, HEIGHT, MARGIN = 4, 352, 12, 8


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def packet(source_tag: str, camera: str, frame: int):
    if camera not in "abc" or len(camera) != 1 or not 0 <= frame < 65536 or len(source_tag) != 8:
        raise ValueError("Invalid rehearsal frame code")
    body = MAGIC+bytes.fromhex(source_tag)+camera.encode()+frame.to_bytes(2, "big")
    return body+binascii.crc_hqx(body, 0xffff).to_bytes(2, "big")


def strip(source_tag, camera, frame):
    row = b"".join(bytes([235 if byte & (1 << bit) else 16])*CELL
                   for byte in packet(source_tag, camera, frame) for bit in range(7, -1, -1))
    return row*HEIGHT


def decode_strip(pixels):
    if len(pixels) != WIDTH*HEIGHT:
        return None
    bits = []
    for bit in range(88):
        values = [pixels[y*WIDTH+bit*CELL+x] for y in range(4, 8) for x in (1, 2)]
        average = sum(values)/len(values)
        if 70 < average < 180:
            return None
        bits.append(int(average >= 180))
    raw = bytes(sum(bits[index*8+bit] << (7-bit) for bit in range(8)) for index in range(11))
    return decode_packet(raw)


def decode_packet(raw):
    if len(raw) != 11 or raw[:2] != MAGIC or raw[6] not in b"abc" or binascii.crc_hqx(raw[:9], 0xffff) != int.from_bytes(raw[9:], "big"):
        return None
    return {"source_tag": raw[2:6].hex(), "camera": chr(raw[6]), "frame": int.from_bytes(raw[7:9], "big")}


def verify_video(path, source_tag, camera, frames):
    result = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-an",
        "-vf", f"crop={WIDTH}:{HEIGHT}:iw-{WIDTH+MARGIN}:ih-{HEIGHT+MARGIN},format=gray",
        "-fps_mode", "passthrough", "-f", "rawvideo", "pipe:1"], capture_output=True, check=True, timeout=60)
    size = WIDTH*HEIGHT
    if len(result.stdout) != frames*size:
        raise ValueError("Frame-code output length differs from the source")
    for number in range(frames):
        code = decode_strip(result.stdout[number*size:(number+1)*size])
        if code != {"source_tag": source_tag, "camera": camera, "frame": number}:
            raise ValueError(f"Frame-code verification failed at {camera}/{number}")
    return {"verified": True, "frames": frames, "method": "all-frame-crc16-and-sequence"}


def prepare_sources(source_dir: Path, destination: Path):
    """Create a new immutable, frame-number-preserving source generation."""
    parent_path = source_dir/"manifest.json"
    parent_digest = digest(parent_path)
    parent = json.loads(parent_path.read_text())
    tag = parent_digest[:8]
    if parent.get("fps") != 30:
        raise ValueError("Frame-coded rehearsal requires 30 fps originals")
    if any(digest(source_dir/camera["file"]) != camera["sha256"] for camera in parent["cameras"]):
        raise ValueError("An original source was modified")
    output = destination/f"{source_dir.name}-{parent_digest[:16]}-framecode-v1"
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output/"manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("parent_manifest_sha256") != parent_digest:
            raise ValueError("Frame-code source provenance changed")
        if any(digest(output/camera["file"]) != camera["sha256"] for camera in manifest["cameras"]):
            raise ValueError("An immutable frame-coded source was modified")
        return output
    cameras = []
    for camera in parent["cameras"]:
        original = source_dir/camera["file"]
        if digest(original) != camera["sha256"]:
            raise ValueError("An original source was modified")
        info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,nb_frames,start_time", "-of", "json", str(original)]))["streams"][0]
        frames = int(info["nb_frames"])
        if (info["width"], info["height"], info["r_frame_rate"]) != (960, 540, "30/1") or frames != round(camera["duration"]*30) or float(info.get("start_time", 0)) != 0:
            raise ValueError("Frame-coded rehearsal requires zero-based 960x540/30 fps source frames")
        target = output/camera["file"]
        if not target.exists():
            pixels = b"".join(strip(tag, camera["id"], frame) for frame in range(frames))
            with tempfile.TemporaryDirectory(prefix="framecode-", dir=output) as temporary:
                rendered = Path(temporary)/"camera.mp4"
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(original),
                    "-f", "rawvideo", "-pixel_format", "gray", "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", "30", "-i", "pipe:0",
                    "-filter_complex", f"[0:v][1:v]overlay=x=main_w-{WIDTH+MARGIN}:y=main_h-{HEIGHT+MARGIN}:shortest=1[v]",
                    "-map", "[v]", "-map", "0:a:0", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-profile:v", "baseline", "-pix_fmt", "yuv420p", "-g", "30", "-bf", "0", "-c:a", "copy",
                    "-movflags", "+faststart", str(rendered)], input=pixels, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=120)
                verify_video(rendered, tag, camera["id"], frames)
                # Atomic no-overwrite publication; another writer cannot replace originals.
                target.hardlink_to(rendered)
        verification = verify_video(target, tag, camera["id"], frames)
        cameras.append({"id": camera["id"], "file": camera["file"], "duration": frames/30,
            "sha256": digest(target), "parent_sha256": camera["sha256"], "parent_file": str(original.resolve()),
            "frame_code_verification": verification})
    manifest = {"kind": "frame-coded-rehearsal-derivative", "fps": 30, "duration": parent["duration"],
        "parent_manifest_sha256": parent_digest, "parent_kind": parent["kind"], "source_tag": tag,
        "frame_code": {"version": 1, "width": WIDTH, "height": HEIGHT, "margin": MARGIN, "cell": CELL},
        "description": "Versioned rehearsal sources with a visible camera/source/frame code. Parent originals preserved.", "cameras": cameras}
    with manifest_path.open("x") as handle:
        handle.write(json.dumps(manifest, indent=2)+"\n")
    return output
