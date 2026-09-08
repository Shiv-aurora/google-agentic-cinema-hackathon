import pytest
from services.api.store import Store


def test_state_event_and_retry_survive_restart(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    doc, token = store.create()
    assert store.authorize(doc["id"], token)
    assert not store.authorize(doc["id"], "wrong")
    request = {"kind": "arm"}
    assert store.command(doc["id"], "unique-id", request) is None
    doc["state"] = "ARMED"
    store.save(doc, "command.arm.applied", {})
    store.complete(doc["id"], "unique-id", {"status": "applied"})
    assert store.command(doc["id"], "unique-id", request) == {"status": "applied"}
    with pytest.raises(ValueError):
        store.command(doc["id"], "unique-id", {"kind": "roll"})
    recovered = Store(tmp_path / "state.sqlite")
    assert recovered.get(doc["id"])["state"] == "INTERRUPTED"
    assert recovered.authorize(doc["id"], token)
    assert recovered.events(doc["id"])[0]["kind"] == "coordinator.recovered"
    assert recovered.command(doc["id"], "unique-id", request) == {"status": "applied"}


def test_sessions_do_not_share_keys(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    a, token_a = store.create()
    b, token_b = store.create()
    assert not store.authorize(a["id"], token_b)
    assert not store.authorize(b["id"], token_a)


def test_restart_expires_controls_and_marks_unfinished_work(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    doc, _ = store.create()
    doc.update(state="RECORDING", hold=True, override_until=99999, active_take="take-1",
               performance={"status": "TRACKING"}, queued_direction={"status": "WAITING"})
    doc["takes"] = [{"id": "take-1", "state": "RECORDING", "edits": [
        {"id": "render-1", "status": "RENDERING"}, {"id": "saved-1", "status": "READY"}]}]
    store.save(doc, "test.started", {})
    recovered = Store(tmp_path / "state.sqlite").get(doc["id"])
    assert recovered["state"] == "INTERRUPTED"
    assert recovered["takes"][0]["state"] == "INTERRUPTED"
    assert recovered["takes"][0]["edits"][0]["status"] == "FAILED"
    assert recovered["takes"][0]["edits"][1]["status"] == "READY"
    assert recovered["queued_direction"]["status"] == "EXPIRED"
    assert recovered["performance"]["status"] == "STOPPED"
    assert recovered["hold"] is False and recovered["override_until"] == 0
    assert recovered["control_epoch"] > doc["control_epoch"]
