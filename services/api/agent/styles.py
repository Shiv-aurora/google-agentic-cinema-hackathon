"""Small, explicit directing vocabularies for the live demo."""

DIRECTING_PRESETS = {
    "classic": {
        "name": "Classic coverage",
        "description": "Establish wide, then use clear shot-reverse-shot coverage.",
        "prompt": "Favor the current speaker, use the wide to re-establish geography, and avoid unnecessary cuts.",
        "minimum_hold": 2.5,
    },
    "reaction": {
        "name": "Reaction first",
        "description": "Let the listener carry emotional turns.",
        "prompt": "Favor the listener after consequential lines and hold reactions rather than mechanically following every speaker.",
        "minimum_hold": 3.0,
    },
    "patient": {
        "name": "Wide and patient",
        "description": "Prefer the two-shot and cut only for a meaningful beat.",
        "prompt": "Stay on the wide two-shot by default. Use a close-up only when the recognized line marks a meaningful reveal.",
        "minimum_hold": 5.0,
    },
    "tension": {
        "name": "Rising tension",
        "description": "Begin composed, then tighten as the exchange develops.",
        "prompt": "Use the wide early, increasingly favor close-ups later in the screenplay, and use reactions to sharpen tension.",
        "minimum_hold": 1.8,
    },
}

DEFAULT_DIRECTING_PRESET = "classic"


def directing_style(doc):
    key = doc.get("directing_preset", DEFAULT_DIRECTING_PRESET)
    if key not in DIRECTING_PRESETS:
        key = DEFAULT_DIRECTING_PRESET
    return key, DIRECTING_PRESETS[key]
