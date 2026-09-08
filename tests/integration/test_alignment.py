import subprocess
import json
from pathlib import Path

import pytest

from services.worker.alignment import match_frames, video_frames
from services.worker import alignment


def test_recovers_offset_and_rejects_drift_loss_and_ambiguous_frames():
    reference = [{"pts": n/30, "hash": str(n)} for n in range(180)]
    received = [{"pts": i/30, "hash": str(i+47)} for i in range(80)]
    result = match_frames(reference, received)
    assert result["verified"] and result["first_source_frame"] == 47
    assert not match_frames(reference, received[:35]+received[36:])["verified"]
    drifted = [{**frame, "pts": frame["pts"]*1.1} for frame in received]
    assert not match_frames(reference, drifted)["verified"]
    repeated = [{"pts": n/30, "hash": "same"} for n in range(80)]
    assert not match_frames(repeated, repeated)["verified"]


def test_real_remux_recovers_known_offset_to_one_frame(tmp_path):
    source = Path("data/fixtures/camera-a.mp4")
    if not source.exists():
        pytest.skip("Generate owned fixtures first")
    clipped = tmp_path/"offset.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", "3", "-i", str(source),
        "-t", "2", "-map", "0:v:0", "-c", "copy", str(clipped)], check=True, timeout=15)
    result = match_frames(video_frames(source), video_frames(clipped))
    assert result["verified"], result
    assert abs(result["first_source_frame"]-90) <= 1


def test_verified_fragments_must_cover_the_requested_source_range(tmp_path, monkeypatch):
    source = tmp_path/"source.mp4"
    source.write_bytes(b"test source")
    recorded = tmp_path/"recorded.mp4"
    recorded.write_bytes(b"test recording")
    (tmp_path/"manifest.json").write_text(json.dumps({"cameras": [
        {"id": cam, "file": source.name, "sha256": alignment.sha256(source)} for cam in "abc"]}))
    reference = [{"pts": n/30, "hash": str(n)} for n in range(180)]
    received = [{"pts": n/30, "hash": str(n+60)} for n in range(60)]
    monkeypatch.setattr(alignment, "source_frames", lambda *args: reference)
    monkeypatch.setattr(alignment, "video_frames", lambda *args: received)
    recordings = {cam: [{"file": recorded.name}] for cam in "abc"}
    valid = alignment.inspect_take(tmp_path, tmp_path, recordings, {cam: 2 for cam in "abc"}, 2)
    assert valid["verified"]
    missing_opening = alignment.inspect_take(tmp_path, tmp_path, recordings, {cam: 0 for cam in "abc"}, 2)
    assert not missing_opening["verified"]
    assert missing_opening["cameras"]["a"]["segments"][0]["verified"]
