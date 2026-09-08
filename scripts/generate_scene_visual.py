"""Google-only original cinematic animatic plate, with reproducible provenance."""
import datetime
import hashlib
import json
from pathlib import Path

from google import genai
from google.genai import types

from services.api.config import PROJECT, google_credentials

PROMPT = """Create one exquisite cinematic illustrated film still for an original intimate drama called The Last Train.
Landscape 16:9, two fictional adults around age 30 seated opposite one another in a nearly empty vintage train compartment at night.
The man, Tom, sits on the LEFT third of frame, wearing a charcoal-brown wool jacket over a dark shirt, short dark slightly tousled hair,
thoughtful restrained expression. The woman, Bella, sits on the RIGHT third, wearing a muted ochre coat, shoulder-length dark wavy hair,
emotionally guarded eyes, holding a small old paper train ticket in her hands. Both faces visible in three-quarter profile, looking toward each other.
Medium-wide two-shot, both shown from chest to head with comfortable headroom. Keep each face in its respective third so this same image
can support derived close-up crops. The table and a small empty space separate them. Rainy dark window centered behind them with cool teal
reflections; warm amber practical lamps light their faces. Muted forest green upholstery, dark wood, brass details. Strong warm/cool separation,
deep shadows but readable faces, subtle atmospheric grain, premium painterly photoreal concept-art finish, restrained cinematic framing,
emotion through the distance between two people. Original fictional faces, not celebrities. No other people. No text, logos, lettering, or visible watermark.
This will be openly labeled a synthetic still-frame animatic, not a real live-action recording."""


def main():
    root = Path("assets/demo/last-train-v1")
    root.mkdir(parents=True, exist_ok=True)
    target = root/"scene-plate.png"
    if target.exists():
        print("Scene plate exists; not overwriting an original asset.")
        return
    model = "gemini-3.1-flash-image"
    client = genai.Client(vertexai=True, project=PROJECT, location="global", credentials=google_credentials(),
        http_options=types.HttpOptions(timeout=90000, retry_options=types.HttpRetryOptions(attempts=1)))
    try:
        response = client.models.generate_content(model=model, contents=PROMPT,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"],
                image_config=types.ImageConfig(aspect_ratio="16:9", image_size="2K"), max_output_tokens=8192))
        generated = next((part.inline_data for part in response.parts or [] if part.inline_data and part.inline_data.mime_type.startswith("image/")), None)
        if not generated:
            raise RuntimeError("Google Gemini returned no usable scene image")
        target.write_bytes(generated.data)
        (root/"provenance.json").write_text(json.dumps({"provider":"Google Cloud Vertex AI", "model":model,"project":PROJECT,
            "created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"prompt":PROMPT,
            "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
            "disclosure":"Original Google-generated still plate. Animatic views are derived crops, not independent live-action angles."},indent=2)+"\n")
        print(json.dumps({"status":"created","path":str(target),"bytes":target.stat().st_size,"model":model}))
    finally:
        client.close()


if __name__ == "__main__":
    main()
