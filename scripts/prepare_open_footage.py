"""Build synchronized virtual cameras from one openly licensed live-action master."""
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    asset_root = Path("assets/demo/open-cafe-v1")
    source = asset_root / "master-original.mp4"
    provenance = json.loads((asset_root / "provenance.json").read_text())
    if digest(source) != provenance["source_sha256"]:
        raise ValueError("The downloaded Pexels master does not match its recorded provenance")

    output_root = Path("data/scenes/open-cafe-v1")
    output_root.mkdir(parents=True, exist_ok=True)
    audio_root = Path("data/scenes/last-train-v1")
    audio_manifest = json.loads((audio_root / "audio-manifest.json").read_text())
    if digest(audio_root / "master.wav") != audio_manifest["sha256"]:
        raise ValueError("The Google dialogue master does not match its manifest")

    # Crop rectangles are 16:9 windows on the 4096x2160 master. A and B isolate
    # each performer; C retains the original two-shot. All three preserve one
    # source clock and receive the same 60-second rehearsal audio.
    crops = {
        "a": "crop=2048:1152:0:360",
        "b": "crop=2048:1152:2048:360",
        "c": "crop=4096:2160:0:0",
    }
    crop_metadata = {
        "a": [2048, 1152, 0, 360],
        "b": [2048, 1152, 2048, 360],
        "c": [4096, 2160, 0, 0],
    }
    cameras = []
    for camera, crop in crops.items():
        output = output_root / f"camera-{camera}.mp4"
        if not output.exists():
            filters = f"{crop},scale=960:540,fps=30,tpad=stop_mode=clone:stop_duration=20,trim=duration=60,setpts=PTS-STARTPTS"
            subprocess.run([
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
                "-i", str(source), "-i", str(audio_root / "master.wav"),
                "-map", "0:v:0", "-map", "1:a:0", "-vf", filters, "-t", "60",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-profile:v", "baseline",
                "-pix_fmt", "yuv420p", "-bf", "0", "-g", "30", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(output),
            ], check=True)
        thumbnail = output_root / f"camera-{camera}.jpg"
        if not thumbnail.exists():
            subprocess.run([
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
                "-ss", "12", "-i", str(output), "-frames:v", "1", "-q:v", "3", str(thumbnail),
            ], check=True)
        cameras.append({
            "id": camera,
            "file": output.name,
            "duration": 60,
            "sha256": digest(output),
            "derived_crop": crop_metadata[camera],
            "source_clock": {"epoch": "open-cafe-v1", "offset_seconds": 0},
        })
        print(f"Verified open-footage camera {camera.upper()}", flush=True)

    manifest = {
        "kind": "open-live-action-derived-views",
        "duration": 60,
        "fps": 30,
        "description": "Three synchronized virtual-camera crops derived from one openly licensed live-action master, with fictional Google-voiced rehearsal dialogue. These are not independent physical cameras or lip-synced performances.",
        "source_sha256": provenance["source_sha256"],
        "source_page": provenance["source_page"],
        "license": provenance["license"],
        "license_url": provenance["license_url"],
        "creator": provenance["creator"],
        "audio_sha256": audio_manifest["sha256"],
        "cameras": cameras,
    }
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Open-footage outputs changed; create a new source version")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    preview = asset_root / "scene-preview.jpg"
    if not preview.exists():
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
            "-ss", "12", "-i", str(output_root / "camera-c.mp4"), "-frames:v", "1", "-q:v", "3", str(preview),
        ], check=True)


if __name__ == "__main__":
    main()
