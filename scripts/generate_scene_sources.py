"""Attach original Google dialogue to independent test-camera video sources.

These are dialogue test charts, not yet the final cinematic presentation.
"""
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    root = Path("data/scenes/last-train-v1")
    audio = json.loads((root / "audio-manifest.json").read_text())
    cameras = []
    for cam in "abc":
        target = root / f"camera-{cam}.mp4"
        if not target.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
                "-i", f"data/fixtures/camera-{cam}.mp4", "-i", str(root / "master.wav"),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", "-t", "60", str(target)], check=True)
        cameras.append({"id": cam, "file": target.name, "duration": 60,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    # Runtime manifest intentionally excludes all line/voice timing ground truth.
    manifest = {"kind": "test-charts-with-original-google-dialogue", "duration": 60, "fps": 30,
        "description": "Three test-chart views with shared original Google-voiced dialogue. Not final cinematic footage.",
        "cameras": cameras, "audio_sha256": audio["sha256"]}
    path = root / "manifest.json"
    if path.exists():
        assert json.loads(path.read_text()) == manifest, "Scene sources changed; create a new source version"
    else:
        path.write_text(json.dumps(manifest, indent=2)+"\n")
    print("Verified 3 dialogue test-camera sources. Evaluation timing stays separate.")


if __name__ == "__main__":
    main()
