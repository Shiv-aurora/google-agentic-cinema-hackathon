"""Owned Google-voiced director commands for repeatable virtual microphone tests."""
import io
import json
import wave
from pathlib import Path

from google.cloud import texttospeech

from services.api.config import google_credentials


def main():
    root = Path("data/voice-fixtures")
    root.mkdir(parents=True, exist_ok=True)
    client = texttospeech.TextToSpeechClient(credentials=google_credentials())
    phrases = {"roll": "Roll cameras.", "hold": "Stay on Bella.", "wide": "Go wide.", "cut": "Cut.", "queue": "Go wide after Tom's next line."}
    for name, text in phrases.items():
        path = root/f"{name}.wav"
        if path.exists():
            continue
        response = client.synthesize_speech(input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(language_code="en-US",name="en-US-Neural2-J"),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16,sample_rate_hertz=48000), timeout=30)
        with wave.open(io.BytesIO(response.audio_content),"rb") as source:
            audio = source.readframes(source.getnframes())
        with wave.open(str(path),"wb") as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
            output.writeframes(bytes(48000)+audio+bytes(48000*3*2))
    (root/"provenance.json").write_text(json.dumps({"provider":"Google Cloud Text-to-Speech","voice":"en-US-Neural2-J","phrases":phrases},indent=2))
    print("Verified original Google-voiced microphone fixtures.")


if __name__ == "__main__":
    main()
