"""Browser-reported composition evidence, kept separate from source alignment."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from services.media.framecode import decode_packet


class MonitorReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=8, max_length=64)
    browser_id: str = Field(min_length=8, max_length=64)
    take_id: str = Field(min_length=8, max_length=64)
    clock_epoch: str = Field(min_length=8, max_length=64)
    camera: Literal["a", "b", "c"]
    decision_time: float = Field(ge=0, le=60)
    kind: Literal["applied", "stalled"]
    browser_ms: float = Field(ge=0, le=1e12)
    player_epoch: str | None = Field(default=None, min_length=8, max_length=64)
    media_time: float | None = Field(default=None, ge=0, le=1e9)
    presented_frames: int | None = Field(default=None, ge=0, le=1e9)
    callback_lateness_ms: float | None = Field(default=None, ge=-1000, le=60000)
    stalled_for_ms: float = Field(default=0, ge=0, le=60000)
    fallback_camera: Literal["a", "b", "c"] | None = None
    source_packet_hex: str | None = Field(default=None, pattern="^[0-9a-f]{22}$")

    @model_validator(mode="after")
    def coherent(self):
        if self.kind == "applied" and (self.media_time is None or self.player_epoch is None):
            raise ValueError("An applied observation requires a composed frame and player epoch")
        if self.fallback_camera and (self.kind != "stalled" or self.stalled_for_ms < 2000 or self.fallback_camera == self.camera):
            raise ValueError("Fallback requires a stalled monitor and a different camera")
        return self


def record_observation(doc, report: MonitorReport, received_monotonic, healthy_cameras):
    """Returns evidence, duplicate flag, fallback flag. Caller holds session lock."""
    take = next((t for t in doc["takes"] if t["id"] == report.take_id), None)
    if not take or doc["active_take"] != report.take_id or doc["state"] != "RECORDING" or take.get("clock_epoch") != report.clock_epoch:
        raise ValueError("Monitor report belongs to an inactive take or clock epoch")
    observations = take.setdefault("monitor_observations", [])
    payload = report.model_dump()
    prior = next((item for item in observations if item["report"]["id"] == report.id), None)
    if prior:
        if prior["report"] != payload:
            raise ValueError("Observation ID was already used for another report")
        return prior, True, False
    if len(observations) >= 240:
        raise ValueError("This take's monitor evidence allowance is exhausted")
    decision = next((d for d in take["decisions"] if d["camera"] == report.camera and math.isclose(d["time"], report.decision_time, abs_tol=1e-6)), None)
    if decision is None:
        raise ValueError("Monitor report does not identify an accepted camera decision")
    received_at = max(0, received_monotonic-take["start_monotonic"])
    current = decision is take["decisions"][-1] and doc["selected_camera"] == report.camera
    evidence = {"report": payload, "received_at": received_at, "current_decision": current,
                "scope": "Client-reported compositor frame; media PTS is not a verified source-frame time"}
    if report.source_packet_hex:
        code = decode_packet(bytes.fromhex(report.source_packet_hex))
        if not code or code["source_tag"] != take.get("source_tag") or code["camera"] != report.camera or code["frame"] >= take.get("source_frame_counts", {}).get(report.camera, 0):
            raise ValueError("Displayed frame code does not match this take's source")
        evidence["decoded_source_frame"] = code
        evidence["scope"] = "CRC-checked source pixels read during a compositor callback; physical display/capture time is not certified"
    fallback = bool(current and report.kind == "stalled" and report.fallback_camera in healthy_cameras
                    and received_at-decision["time"] >= 2)
    evidence["fallback_applied"] = fallback
    observations.append(evidence)
    if fallback:
        at = round(received_at*30)/30
        take["decisions"].append({"camera": report.fallback_camera, "time": at,
            "reason": "Director browser reported stalled program playback", "source": "monitor-fallback"})
        doc.update(selected_camera=report.fallback_camera, hold=False, override_until=0,
                   control_epoch=doc.get("control_epoch", 0)+1,
                   note="Monitor playback stalled. Switched to a progressing camera; original recordings continue.")
    return evidence, False, fallback
