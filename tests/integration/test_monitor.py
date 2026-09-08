from copy import deepcopy

import pytest
from pydantic import ValidationError

from services.api.monitor import MonitorReport, record_observation
from services.media.framecode import packet


def document():
    return {"state": "RECORDING", "active_take": "test-take", "selected_camera": "a", "hold": True,
            "takes": [{"id": "test-take", "clock_epoch": "epoch-one", "start_monotonic": 100,
                       "decisions": [{"camera": "a", "time": 0}]}]}


def report(**changes):
    return MonitorReport(**({"id": "report-one", "browser_id": "browser-one", "take_id": "test-take",
        "clock_epoch": "epoch-one", "camera": "a", "decision_time": 0, "kind": "applied",
        "browser_ms": 600, "player_epoch": "player-one", "media_time": 42.75, **changes}))


def test_composition_evidence_is_separate_and_idempotent():
    doc = document()
    evidence, duplicate, fallback = record_observation(doc, report(), 103, {"a", "b", "c"})
    assert evidence["received_at"] == 3
    assert evidence["report"]["media_time"] == 42.75  # Never substitute this as source/take time.
    assert not duplicate and not fallback
    assert len(doc["takes"][0]["decisions"]) == 1
    assert record_observation(doc, report(), 104, {"a"})[1]
    assert len(doc["takes"][0]["monitor_observations"]) == 1
    with pytest.raises(ValueError, match="already used"):
        record_observation(doc, report(media_time=99), 105, {"a"})


def test_stalled_monitor_fallback_records_a_cut_without_losing_sources():
    doc = document()
    evidence, _, fallback = record_observation(doc, report(kind="stalled", stalled_for_ms=2500, fallback_camera="c"), 103, {"a", "c"})
    assert fallback and evidence["fallback_applied"]
    assert doc["selected_camera"] == "c" and doc["hold"] is False
    assert doc["state"] == "RECORDING"
    assert doc["takes"][0]["decisions"][-1]["source"] == "monitor-fallback"
    assert doc["takes"][0]["decisions"][-1]["time"] == 3


def test_late_or_unhealthy_observation_cannot_override_new_direction():
    for healthy in ({"a"}, {"a", "c"}):
        doc = document()
        if "c" in healthy:
            doc["takes"][0]["decisions"].append({"camera": "b", "time": 2})
            doc["selected_camera"] = "b"
        before = deepcopy(doc)
        assert not record_observation(doc, report(kind="stalled", stalled_for_ms=2500, fallback_camera="c"), 104, healthy)[2]
        assert doc["selected_camera"] == before["selected_camera"]
        assert doc["takes"][0]["decisions"] == before["takes"][0]["decisions"]


def test_inactive_epoch_and_fabricated_decision_are_rejected():
    for changes in ({"clock_epoch": "epoch-old"}, {"take_id": "take-old"}, {"decision_time": 1}):
        with pytest.raises(ValueError):
            record_observation(document(), report(**changes), 103, {"a"})
    doc = document(); doc["state"] = "READY"
    with pytest.raises(ValueError):
        record_observation(doc, report(), 103, {"a"})


def test_report_requires_real_frame_fields_and_finite_values():
    for changes in ({"media_time": None}, {"browser_ms": float("nan")},
                    {"fallback_camera": "c"}, {"kind": "stalled", "stalled_for_ms": 100, "fallback_camera": "c"}):
        with pytest.raises(ValidationError):
            report(**changes)


def test_displayed_source_frame_is_validated_separately_from_browser_pts():
    doc=document();doc["takes"][0].update(source_tag="a1b2c3d4",source_frame_counts={"a":1800})
    evidence,_,_=record_observation(doc,report(media_time=0,source_packet_hex=packet("a1b2c3d4","a",47).hex()),103,{"a"})
    assert evidence["decoded_source_frame"]["frame"] == 47
    assert evidence["report"]["media_time"] == 0
    with pytest.raises(ValueError):
        record_observation(doc,report(id="report-two",source_packet_hex=packet("a1b2c3d4","b",47).hex()),103,{"a"})
