"""Queued spoken direction binds a future line and yields to a manual hold."""
import json
import time
import uuid
from pathlib import Path

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000",timeout=40) as client:
        result = client.post("/api/sessions").json()
        doc = result["session"]
        client.headers["Authorization"] = f"Bearer {result['token']}"
        route = f"/api/sessions/{doc['id']}"
        client.put(route+"/scene",json={"title":doc["title"],"script":doc["script"],"source_set":"last-train-v1"}).raise_for_status()
        def command(kind, camera=None):
            current = client.get(route).json()
            response = client.post(route+"/commands",json={"id":uuid.uuid4().hex,"kind":kind,"camera":camera,"expected_revision":current["revision"]})
            response.raise_for_status()
            return response.json()["session"]
        command("arm")
        doc = command("roll")
        command("hold","b")
        response = client.post(route+"/voice",data={"id":uuid.uuid4().hex,"take_id":doc["active_take"]},
            files={"audio":("queue.wav",Path("data/voice-fixtures/queue.wav").read_bytes(),"audio/wav")})
        if response.status_code != 200:
            command("cut")
            raise AssertionError(response.text)
        queued = response.json()["session"]["queued_direction"]
        assert queued["status"] == "WAITING" and queued["camera"] == "c", queued
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            doc = client.get(route).json()
            assert doc["selected_camera"] == "b" and doc["hold"]
            if doc["queued_direction"]["status"] == "DEFERRED":
                break
            time.sleep(.3)
        else:
            command("cut")
            raise AssertionError("The bound line did not complete")
        doc = command("release")
        assert doc["selected_camera"] == "c" and doc["queued_direction"]["status"] == "APPLIED"
        doc = command("cut")
        Path("artifacts/queued-voice-smoke.json").write_text(json.dumps({"status":"passed","session_id":doc["id"],"queued":doc["queued_direction"],"events":client.get(route+"/events").json()},indent=2))
        print(json.dumps({"status":"passed","target_line":queued["target_line_id"],"manual_hold_precedence":True,"queued_wide_applied":True}))


if __name__ == "__main__":
    main()
