"""Clock bounds and measured received-frame mappings, not capture timestamps."""
from collections import defaultdict
from statistics import mean

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from services.media.framecode import decode_packet


class ClockProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    browser_id: str = Field(min_length=8, max_length=64)
    take_id: str = Field(min_length=8, max_length=64)


class FrameRead(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    camera: Literal["a", "b", "c"]
    packet_hex: str = Field(pattern="^[0-9a-f]{22}$")
    stream_id: str = Field(min_length=1, max_length=128)
    read_start_ms: float = Field(ge=0, le=1e12)
    read_end_ms: float = Field(ge=0, le=1e12)


class FrameReadBatch(ClockProbeRequest):
    id: str = Field(min_length=8, max_length=64)
    clock_epoch: str = Field(min_length=8, max_length=64)
    probe_id: str = Field(min_length=8, max_length=64)
    client_send_ms: float = Field(ge=0, le=1e12)
    client_receive_ms: float = Field(ge=0, le=1e12)
    frames: list[FrameRead] = Field(min_length=1, max_length=3)


def offset_bounds(client_send, client_receive, server_receive, server_send):
    """Server minus client clock; all arguments are seconds.

    Nonnegative transit/processing times give an interval without assuming
    symmetric network delay. Finite clock-rate error is handled by the caller.
    """
    if not 0 <= client_receive-client_send <= 2 or not 0 <= server_send-server_receive <= client_receive-client_send:
        raise ValueError("Invalid or overly slow clock exchange")
    return server_send-client_receive, server_receive-client_send


def transform_batch(batch: FrameReadBatch, probe, take, now):
    if probe["browser_id"] != batch.browser_id or now-probe["server_send"] > 15:
        raise ValueError("Clock probe expired or belongs to another browser")
    lower, upper = offset_bounds(batch.client_send_ms/1000, batch.client_receive_ms/1000,
                                 probe["server_receive"], probe["server_send"])
    if len({item.camera for item in batch.frames}) != len(batch.frames):
        raise ValueError("A frame batch must not repeat a camera")
    result = []
    for item in batch.frames:
        code = decode_packet(bytes.fromhex(item.packet_hex))
        if not code or code["source_tag"] != take["source_tag"] or code["camera"] != item.camera or code["frame"] >= take["source_frame_counts"][item.camera]:
            raise ValueError("Frame code does not match this take's source generation")
        if not batch.client_receive_ms <= item.read_start_ms <= item.read_end_ms <= batch.client_receive_ms+12000 or item.read_end_ms-item.read_start_ms > 100:
            raise ValueError("Pixel read is stale or has excessive uncertainty")
        # 200 ppm allowance over the short probe lifetime, explicitly retained.
        drift = (item.read_end_ms-batch.client_receive_ms)/1000*.0002
        result.append({"camera": item.camera, "source_tag": code["source_tag"], "source_frame": code["frame"],
            "source_seconds": code["frame"]/30, "browser_id": batch.browser_id, "stream_id": item.stream_id,
            "session_time_lower": item.read_start_ms/1000+lower-take["start_monotonic"]-drift,
            "session_time_upper": item.read_end_ms/1000+upper-take["start_monotonic"]+drift,
            "clock_offset_lower": lower, "clock_offset_upper": upper, "clock_drift_allowance_seconds": drift})
    return result


def fit_received_clocks(samples):
    """Keep different receivers/stream epochs separate; never hide outliers."""
    groups = defaultdict(list)
    for sample in samples:
        groups[(sample["browser_id"], sample["stream_id"], sample["camera"])].append(sample)
    mappings = []
    for (browser, stream, camera), items in groups.items():
        base = {"browser_id": browser, "stream_id": stream, "camera": camera, "samples": len(items),
                "scope": "Source frames at browser pixel-read time, not physical capture or server decision acceptance"}
        xs = [item["source_seconds"] for item in items]
        ys = [(item["session_time_lower"]+item["session_time_upper"])/2 for item in items]
        if len(items) < 6 or max(xs)-min(xs) < 4:
            mappings.append({**base, "calibrated": False, "reason": "Need six samples spanning four source seconds"})
            continue
        xbar, ybar = mean(xs), mean(ys)
        scale = sum((x-xbar)*(y-ybar) for x, y in zip(xs, ys))/sum((x-xbar)**2 for x in xs)
        offset = ybar-scale*xbar
        residual = max(abs(y-(offset+scale*x)) for x, y in zip(xs, ys))
        clock_half = max((item["session_time_upper"]-item["session_time_lower"])/2 for item in items)
        uncertainty = residual+clock_half+abs(scale)/30
        progressing = all(b >= a for a, b in zip(xs, xs[1:]))
        calibrated = progressing and .98 <= scale <= 1.02 and uncertainty <= .15
        mappings.append({**base, "calibrated": calibrated,
            "reason": "Measured bounded receive-time fit" if calibrated else "Receive timing discontinuity, drift or excessive uncertainty",
            "formula": "session_time = offset_seconds + scale * source_seconds",
            "offset_seconds": offset, "scale": scale, "max_residual_seconds": residual,
            "observed_uncertainty_seconds": uncertainty,
            "source_frame_range": [min(item["source_frame"] for item in items), max(item["source_frame"] for item in items)],
            "extrapolation_verified": False})
    return {"schema_version": 1, "method": "framecode-crc16-plus-bracketed-browser-clock", "mappings": mappings,
            "live_edit_retimed": False, "capture_clock_verified": False}
