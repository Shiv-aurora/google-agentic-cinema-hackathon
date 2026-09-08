"""A deliberately small, validated OTIO subset compiled into actual FFmpeg edits."""
import hashlib
import json
import subprocess
from pathlib import Path

import opentimelineio as otio
from pydantic import BaseModel, Field, model_validator


class Segment(BaseModel):
    camera: str = Field(pattern="^[abc]$")
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    reason: str = "Director selection"

    @model_validator(mode="after")
    def positive(self):
        if self.end <= self.start:
            raise ValueError("A segment must have positive duration")
        return self


def validate_segments(segments: list[Segment], duration: float):
    if not segments or abs(segments[0].start) > 1e-6 or abs(segments[-1].end - duration) > 1e-6:
        raise ValueError("Edit must cover the complete take")
    for left, right in zip(segments, segments[1:]):
        if abs(left.end - right.start) > 1e-6:
            raise ValueError("Edit has a gap or overlap")


def file_hash(path: Path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def make_timeline(edit_id: str, segments: list[Segment], fixtures: Path, duration: float, offsets=None):
    validate_segments(segments, duration)
    offsets = offsets or {cam: 0 for cam in "abc"}
    manifest = json.loads((fixtures / "manifest.json").read_text())
    sources = {cam["id"]: cam for cam in manifest["cameras"]}
    timeline = otio.schema.Timeline(name=edit_id)
    picture = otio.schema.Track(name="Program", kind=otio.schema.TrackKind.Video)
    audio = otio.schema.Track(name="Master audio", kind=otio.schema.TrackKind.Audio)
    for seg in segments:
        source = sources[seg.camera]
        path = fixtures / source["file"]
        if file_hash(path) != source["sha256"]:
            raise ValueError("An original source was modified")
        start_frame = round((seg.start + offsets[seg.camera]) * 30)
        frame_count = round(seg.end * 30) - round(seg.start * 30)
        if start_frame < 0 or start_frame + frame_count > round(source["duration"] * 30) or frame_count <= 0:
            raise ValueError("Edit references unavailable source frames")
        clip = otio.schema.Clip(name=f"Camera {seg.camera.upper()}",
            media_reference=otio.schema.ExternalReference(target_url=str(path.resolve())),
            source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(start_frame,30), otio.opentime.RationalTime(frame_count,30)))
        clip.metadata["clappy"] = {"camera": seg.camera, "reason": seg.reason, "sha256": source["sha256"]}
        picture.append(clip)
    audio_start = round(offsets["c"] * 48000)
    audio.append(otio.schema.Clip(name="Camera C audio", media_reference=otio.schema.ExternalReference(target_url=str((fixtures / sources["c"]["file"]).resolve())),
        source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(audio_start,48000), otio.opentime.RationalTime(round(duration*48000),48000))))
    timeline.tracks.extend([picture,audio])
    timeline.metadata["clappy"] = {"schema_version": 1, "kind": "synthetic-source-conform", "sync": "publisher-clock-estimate"}
    return timeline


def render_timeline(timeline_path: Path, output: Path):
    timeline = otio.adapters.read_from_file(str(timeline_path))
    if len(timeline.tracks) != 2:
        raise ValueError("Only one video and one master audio track are supported")
    picture, audio = timeline.tracks
    if not picture or len(audio) != 1:
        raise ValueError("Invalid simple-cut timeline")
    inputs, filters, labels = [], [], []
    for i, clip in enumerate(picture):
        if not isinstance(clip, otio.schema.Clip) or clip.effects:
            raise ValueError("Unsupported timeline item or effect")
        inputs += ["-i", clip.media_reference.target_url]
        start = int(clip.source_range.start_time.rescaled_to(30).value)
        count = int(clip.source_range.duration.rescaled_to(30).value)
        filters.append(f"[{i}:v]fps=30,trim=start_frame={start}:end_frame={start+count},setpts=PTS-STARTPTS,scale=960:540,setsar=1[v{i}]")
        labels.append(f"[v{i}]")
    master = audio[0]
    inputs += ["-i", master.media_reference.target_url]
    start = master.source_range.start_time.to_seconds()
    duration = master.source_range.duration.to_seconds()
    filters += ["".join(labels) + f"concat=n={len(labels)}:v=1:a=0[video]",
                f"[{len(labels)}:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS[audio]"]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", ";".join(filters), "-map", "[video]", "-map", "[audio]", "-c:v", "libx264", "-preset", "fast",
        "-crf", "21", "-c:a", "aac", "-movflags", "+faststart", str(temporary)], check=True, timeout=180)
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(temporary)]))
    if abs(float(info["format"]["duration"]) - duration) > .1:
        raise ValueError("Rendered duration differs from the timeline")
    temporary.replace(output)
    return {"duration": float(info["format"]["duration"]), "bytes": output.stat().st_size, "sha256": file_hash(output)}
