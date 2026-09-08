import pytest

from services.media.clock import FrameReadBatch, fit_received_clocks, offset_bounds, transform_batch
from services.media.framecode import packet


def test_clock_bounds_include_asymmetric_transit_without_assuming_midpoint_is_truth():
    lower, upper = offset_bounds(10, 10.08, 110.02, 110.03)
    assert lower <= 100 <= upper
    assert abs(lower-99.95) < 1e-8 and abs(upper-100.02) < 1e-8
    with pytest.raises(ValueError):
        offset_bounds(10, 10.01, 110.02, 110.04)


def test_frame_samples_bind_source_camera_epoch_and_clock_bounds():
    values = {"id":"batch-one", "take_id":"take-one", "browser_id":"browser-one", "clock_epoch":"epoch-one",
        "probe_id":"probe-one", "client_send_ms":10000, "client_receive_ms":10080,
        "frames":[{"camera":"b", "stream_id":"stream-one", "packet_hex":packet("a1b2c3d4","b",47).hex(),
                   "read_start_ms":11000, "read_end_ms":11002}]}
    probe = {"browser_id":"browser-one", "server_receive":110.02, "server_send":110.03}
    take = {"source_tag":"a1b2c3d4", "source_frame_counts":{"b":1800}, "start_monotonic":109}
    sample = transform_batch(FrameReadBatch(**values), probe, take, 111.1)[0]
    assert sample["source_frame"] == 47
    assert sample["session_time_lower"] <= 2 <= sample["session_time_upper"]
    with pytest.raises(ValueError):
        transform_batch(FrameReadBatch(**values), probe, {**take,"source_tag":"00000000"},111.1)
    with pytest.raises(ValueError):
        transform_batch(FrameReadBatch(**values), probe, take, 140)


def test_receive_time_fit_reports_delay_drift_and_freeze_without_overclaiming():
    samples=[{"camera":"b","browser_id":"one","stream_id":"epoch", "source_frame":n*30,
              "source_seconds":n,"session_time_lower":n+2-.01,"session_time_upper":n+2+.01} for n in range(10)]
    report=fit_received_clocks(samples)
    mapping=report["mappings"][0]
    assert mapping["calibrated"] and abs(mapping["offset_seconds"]-2)<1e-8 and abs(mapping["scale"]-1)<1e-8
    assert not mapping["extrapolation_verified"] and not report["capture_clock_verified"] and not report["live_edit_retimed"]
    drift=[{**s,"session_time_lower":s["source_seconds"]*1.1,"session_time_upper":s["source_seconds"]*1.1+.01} for s in samples]
    assert not fit_received_clocks(drift)["mappings"][0]["calibrated"]
    freeze=[*samples[:7], *[{**s,"source_seconds":6,"source_frame":180} for s in samples[7:]]]
    assert not fit_received_clocks(freeze)["mappings"][0]["calibrated"]
