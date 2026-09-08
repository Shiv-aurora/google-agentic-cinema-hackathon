"""Conservative nearby-line alignment; screenplay text is never a command."""
import re
from difflib import SequenceMatcher


def script_lines(script):
    lines = []
    for block in script.split("\n\n"):
        parts = block.strip().splitlines()
        if len(parts) >= 2 and parts[0] in ("TOM", "BELLA"):
            lines.append({"id": len(lines), "character": parts[0], "text": " ".join(parts[1:])})
    return lines


def normalize(text):
    return re.findall(r"[a-z0-9]+", text.lower().replace("’", "'"))


class ScriptFollower:
    def __init__(self, script):
        self.lines = script_lines(script)
        self.current = -1

    def observe(self, transcript, *, final=False):
        words = normalize(transcript)
        if len(words) < 2:
            return None
        candidates = []
        # Repetition is possible; jumping arbitrarily to a later reveal is not.
        for line in self.lines[max(0, self.current-1):self.current+4]:
            expected = normalize(line["text"])
            window = words[-max(len(expected)+3, 10):]
            similarity = SequenceMatcher(None, " ".join(window), " ".join(expected)).ratio()
            overlap = len(set(window) & set(expected)) / max(1, len(set(expected)))
            score = .6*similarity + .4*overlap
            candidates.append((score, line))
        candidates.sort(key=lambda x: x[0], reverse=True)
        if not candidates or candidates[0][0] < .6:
            return None
        if len(candidates)>1 and candidates[0][0]-candidates[1][0] < .08:
            return None
        score, line = candidates[0]
        if line["id"] < self.current and (not final or score < .88):
            return None  # Interim hypotheses can shrink; don't rewind the scene.
        previous = self.current
        self.current = line["id"]
        return {**line, "confidence": round(score, 3), "changed": previous != self.current}
