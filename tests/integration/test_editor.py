import json
import subprocess
from pathlib import Path

import opentimelineio as otio
import pytest

from services.worker.editor import Segment, make_timeline, render_timeline, file_hash, validate_segments


def test_rejects_invalid_edit_ranges():
    with pytest.raises(ValueError):
        Segment(camera="a", start=2, end=1)
    with pytest.raises(ValueError):
        validate_segments([Segment(camera="a", start=0, end=1), Segment(camera="b", start=2, end=3)], 3)
    with pytest.raises(ValueError):
        validate_segments([Segment(camera="a", start=1, end=3)], 3)


def frame(path, t):
    return subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
        "-vf", f"select=eq(n\\,{int(t*30)}),crop=30:30:5:5,scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])


def test_otio_roundtrip_and_real_render_match_sources(tmp_path):
    fixtures = Path("data/fixtures").resolve()
    if not (fixtures / "manifest.json").exists():
        pytest.skip("Run scripts/generate_fixtures.py to create owned media")
    before = {p.name: file_hash(p) for p in fixtures.glob("*.mp4")}
    segments = [Segment(camera="c", start=0, end=1), Segment(camera="a", start=1, end=2), Segment(camera="b", start=2, end=3)]
    timeline = make_timeline("test-edit", segments, fixtures, 3)
    path = tmp_path / "cut.otio"
    otio.adapters.write_to_file(timeline, str(path))
    loaded = otio.adapters.read_from_file(str(path))
    assert [c.source_range.start_time.value for c in loaded.tracks[0]] == [0,30,60]
    assert loaded.duration().to_seconds() == 3
    output = tmp_path / "cut.mp4"
    info = render_timeline(path, output)
    assert abs(info["duration"]-3) < .1
    for t, camera in [(0.5,"c"),(.98,"c"),(1.02,"a"),(1.5,"a"),(1.98,"a"),(2.02,"b"),(2.5,"b")]:
        actual, expected = frame(output,t), frame(fixtures/f"camera-{camera}.mp4",t)
        assert max(abs(a-b) for a,b in zip(actual,expected)) < 8, (t,actual,expected)
    streams = json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-of","json",str(output)]))["streams"]
    assert len([s for s in streams if s["codec_type"]=="audio"]) == 1
    assert {p.name: file_hash(p) for p in fixtures.glob("*.mp4")} == before


def test_rejects_unavailable_frames():
    fixtures = Path("data/fixtures").resolve()
    if not (fixtures / "manifest.json").exists():
        pytest.skip("Fixtures unavailable")
    with pytest.raises(ValueError):
        make_timeline("bad", [Segment(camera="a",start=0,end=61)], fixtures, 61)
