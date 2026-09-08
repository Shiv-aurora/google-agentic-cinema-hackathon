"""Exact source-frame identification for Clappy's copy-video virtual cameras.

This proves media identity/relative timing, not frame-locked browser playback or
the physical capture time of a future phone. Re-encoded/ambiguous inputs fail
closed; they need another alignment method, not invented matching evidence.
"""
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from fractions import Fraction
from functools import lru_cache
from pathlib import Path


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def video_frames(path):
    result = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "2", "-i", str(path),
        "-map", "0:v:0", "-an", "-fps_mode", "passthrough", "-f", "framehash", "-hash", "sha256", "pipe:1"],
        capture_output=True, text=True, timeout=45, check=True)
    time_base = None
    frames = []
    for line in result.stdout.splitlines():
        if line.startswith("#tb 0:"):
            time_base = Fraction(line.split(":", 1)[1].strip())
        elif line and not line.startswith("#"):
            fields = [part.strip() for part in line.split(",")]
            if time_base is None or len(fields) != 6:
                raise ValueError("Unsupported framehash output")
            frames.append({"pts": float(int(fields[2])*time_base), "hash": fields[5]})
    if not frames:
        raise ValueError("No decodable video frames")
    return frames


@lru_cache(maxsize=12)
def source_frames(path, digest):
    # Caller verifies the current file digest before consulting this cache.
    return video_frames(path)


def match_frames(reference, received, fps=30):
    positions = defaultdict(list)
    for index, frame in enumerate(reference):
        positions[frame["hash"]].append(index)
    unique = {value: indexes[0] for value, indexes in positions.items() if len(indexes) == 1}
    anchors = [(index, unique[frame["hash"]]) for index, frame in enumerate(received) if frame["hash"] in unique]
    if len(anchors) < min(10, len(received)):
        return {"verified": False, "reason": "Insufficient unique source-frame anchors", "frames": len(received)}
    offsets = Counter(source-index for index, source in anchors)
    offset, agreeing = offsets.most_common(1)[0]
    matched = sum(0 <= index+offset < len(reference) and
                  frame["hash"] == reference[index+offset]["hash"] for index, frame in enumerate(received))
    # A lost/duplicated/reordered frame changes the mapping and must be visible.
    residuals = [(received[index]["pts"]-received[0]["pts"])-index/fps for index in range(len(received))]
    drift = max(residuals)-min(residuals)
    verified = matched == len(received) and agreeing == len(anchors) and drift <= 1/fps+.00001
    return {"verified": verified, "reason": "Exact decoded-frame match" if verified else "Frame identity or media-clock discontinuity",
        "frames": len(received), "matched_frames": matched, "unique_anchors": len(anchors),
        "first_source_frame": offset, "end_source_frame_exclusive": offset+len(received),
        "source_offset_seconds": offset/fps, "recording_first_pts": received[0]["pts"],
        "max_clock_residual_seconds": round(drift, 6), "fps": fps}


def inspect_take(data: Path, fixtures: Path, recordings, offsets=None, duration=None):
    manifest_path = fixtures/"manifest.json"
    manifest = json.loads(manifest_path.read_text())
    report = {"schema_version": 1, "method": "decoded-sha256-frame-match", "manifest_sha256": sha256(manifest_path),
        "scope": "Recorded media to preserved source frames; live command origin remains a clock estimate", "cameras": {}}
    for camera in manifest["cameras"]:
        source = fixtures/camera["file"]
        digest = sha256(source)
        if digest != camera["sha256"]:
            raise ValueError("An original source was modified")
        reference = source_frames(str(source.resolve()), digest)
        segments = []
        for part in recordings.get(camera["id"], []):
            path = data/part["file"]
            try:
                matched = match_frames(reference, video_frames(path))
                segments.append({"file": part["file"], "sha256": sha256(path), **matched})
            except (ValueError, subprocess.SubprocessError) as exc:
                segments.append({"file": part["file"], "verified": False, "reason": str(exc)[:300]})
        segments.sort(key=lambda item: item.get("first_source_frame", -1))
        continuous = all(left.get("end_source_frame_exclusive") == right.get("first_source_frame")
                         for left, right in zip(segments, segments[1:]))
        verified = bool(segments) and continuous and all(part["verified"] for part in segments)
        required_range = None
        if duration is not None:
            first = round((offsets or {}).get(camera["id"], 0)*30)
            required_range = {"first_source_frame": first, "end_source_frame_exclusive": first+round(duration*30)}
            verified = verified and segments[0].get("first_source_frame", first+1) <= first and segments[-1].get("end_source_frame_exclusive", -1) >= required_range["end_source_frame_exclusive"]
        report["cameras"][camera["id"]] = {"verified": verified, "continuous": continuous, "segments": segments,
            "source_file": camera["file"], "source_sha256": digest, "source_frames": len(reference),
            "required_range": required_range, "frames": sum(part.get("frames", 0) for part in segments)}
    report["verified"] = all(camera["verified"] for camera in report["cameras"].values())
    return report
