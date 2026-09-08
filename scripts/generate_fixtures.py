"""Create owned, deterministic media inputs; never overwrite existing originals."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def generate(root: Path, duration: int = 60):
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": "synthetic-test-fixture", "duration": duration, "fps": 30, "cameras": []}
    for key, name, color in [("a", "TOM", "0x273a49"), ("b", "BELLA", "0x524536"), ("c", "WIDE", "0x2f443c")]:
        target = root / f"camera-{key}.mp4"
        # Mark motion, absolute frame number and scene time for boundary assertions.
        filters = (
            f"color=c={color}:s=960x540:r=30:d={duration},"
            "drawgrid=w=80:h=60:t=1:c=white@0.08,"
            "drawbox=x=80:y=80:w=800:h=380:color=white@0.08:t=2,"
            f"drawtext=text='{name} / VIRTUAL CAMERA':fontsize=34:fontcolor=white:x=80:y=110,"
            "drawtext=text='Frame %{n}':fontsize=28:fontcolor=white:x=80:y=170,"
            "drawtext=text='%{pts\\:hms}':fontsize=64:fontcolor=white:x=80:y=230,"
            "drawtext=text='DETERMINISTIC TEST FOOTAGE':fontsize=18:fontcolor=white@0.55:x=80:y=415,"
            "drawtext=text='●':fontsize=40:fontcolor=0xc4ee8d:x='80+mod(t*100,760)':y=340"
        )
        if not target.exists():
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                "-f", "lavfi", "-i", filters,
                "-f", "lavfi", "-i", f"aevalsrc=if(lt(mod(t\\,1)\\,0.025)\\,0.3*sin(2*PI*1000*t)\\,0):s=48000:d={duration}",
                "-c:v", "libx264", "-preset", "fast", "-profile:v", "baseline", "-pix_fmt", "yuv420p",
                "-g", "30", "-bf", "0", "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(target)
            ], check=True)
        info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(target)]))
        manifest["cameras"].append({"id": key, "name": name, "file": target.name,
            "sha256": hashlib.file_digest(target.open("rb"), "sha256").hexdigest(),
            "duration": float(info["format"]["duration"]), "size": target.stat().st_size})
    manifest_path = root / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError("Existing fixture manifest differs; use a new output directory")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/fixtures"))
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()
    generate(args.output, args.duration)
