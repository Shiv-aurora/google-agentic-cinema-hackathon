"""Creative context is bounded and separate from full source/clock audit evidence."""


def take_context(take):
    if not take:
        return None
    fields = ("id", "number", "state", "source_set", "source_directory", "duration",
              "source_offsets", "recordings_verified", "lost_cameras")
    result = {key: take[key] for key in fields if key in take}
    result["decisions"] = take.get("decisions", [])[-40:]
    result["transcripts"] = [{key: event[key] for key in ("text", "final", "confidence", "audio_end") if key in event}
                             for event in take.get("transcripts", [])[-20:]]
    result["edits"] = [{key: edit[key] for key in ("id", "name", "status", "parent_id", "segments") if key in edit}
                       for edit in take.get("edits", [])[-8:]]
    return result
