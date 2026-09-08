"""Live-paced Google recognition of generated scene audio, checked against held-out timing."""
import asyncio
import json
from pathlib import Path

from services.api.agent.script import ScriptFollower
from services.api.agent.speech import ffmpeg_pcm, recognize_stream
from services.api.store import SCRIPT


async def main():
    follower, observed = ScriptFollower(SCRIPT), []
    async def result(event):
        aligned = follower.observe(event["text"])
        if aligned and aligned["changed"]:
            observed.append({"line": aligned, "recognition": event})
            print(json.dumps({"line": aligned["id"], "text": event["text"], "audio_end": event["audio_end"]}), flush=True)
    async with asyncio.timeout(75):
        await recognize_stream(ffmpeg_pcm("data/scenes/last-train-v1/master.wav", realtime=True), result)
    assert {item["line"]["id"] for item in observed} == set(range(6)), observed
    Path("artifacts/speech-smoke.json").write_text(json.dumps({"status": "passed", "observations": observed},indent=2))
    print("PASS: all six screenplay lines were recognized from actual audio.")


if __name__ == "__main__":
    asyncio.run(main())
