"""Create owned synthetic dialogue with Google voices; never copy evaluation timings to the agent."""
import hashlib
import io
import json
import wave
from pathlib import Path

import numpy as np
from google.cloud import texttospeech

from services.api.agent.script import script_lines
from services.api.config import PROJECT, google_credentials
from services.api.store import SCRIPT


def main():
    root = Path("data/scenes/last-train-v1")
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "audio-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        assert hashlib.sha256((root / "master.wav").read_bytes()).hexdigest() == manifest["sha256"]
        print("Verified existing Google-voiced scene audio; not overwriting.")
        return
    client = texttospeech.TextToSpeechClient(credentials=google_credentials())
    rate, duration = 48000, 60
    # Very quiet deterministic station ambience, not another person's recording.
    rng = np.random.default_rng(42)
    master = rng.normal(0, .0008, rate*duration)
    cursor, ground_truth = 3.5, []
    voices = {"TOM": "en-US-Neural2-D", "BELLA": "en-US-Neural2-F"}
    for line in script_lines(SCRIPT):
        destination = root / f"line-{line['id']}.wav"
        if not destination.exists():
            response = client.synthesize_speech(input=texttospeech.SynthesisInput(text=line["text"]),
                voice=texttospeech.VoiceSelectionParams(language_code="en-US", name=voices[line["character"]]),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                    sample_rate_hertz=rate, speaking_rate=.9), timeout=30)
            destination.write_bytes(response.audio_content)
        with wave.open(str(destination), "rb") as audio:
            assert audio.getframerate() == rate and audio.getnchannels() == 1
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(float)/32768
        start = round(cursor*rate)
        master[start:start+len(samples)] += samples*.85
        ground_truth.append({**line, "start": cursor, "end": cursor+len(samples)/rate, "voice": voices[line["character"]]})
        cursor += len(samples)/rate + (4.5 if line["id"] in (3,4,5) else 3.5)
    with wave.open(str(root / "master.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes((np.clip(master,-1,1)*32767).astype("<i2").tobytes())
    manifest = {"kind": "original-synthetic-dialogue", "project": PROJECT, "provider": "Google Cloud Text-to-Speech",
        "script": SCRIPT, "duration": duration, "dialogue_end": ground_truth[-1]["end"],
        "evaluation_only_ground_truth": ground_truth,
        "sha256": hashlib.sha256((root / "master.wav").read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({"status": "created", "lines": len(ground_truth), "duration": duration, "dialogue_end": ground_truth[-1]["end"]}))


if __name__ == "__main__":
    main()
