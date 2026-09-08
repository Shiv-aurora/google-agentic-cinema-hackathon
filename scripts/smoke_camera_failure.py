"""Kill only this test's camera A publisher; verify fallback and honest coverage."""
import json
import argparse
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

import httpx


def main(all_cameras=False):
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        created = client.post("/api/sessions").json()
        route = f"/api/sessions/{created['session']['id']}"
        client.headers["Authorization"] = f"Bearer {created['token']}"

        def command(kind, camera=None, expected=200):
            doc = client.get(route).json()
            result = client.post(route+"/commands", json={"id": uuid.uuid4().hex, "kind": kind,
                "camera": camera, "expected_revision": doc["revision"]})
            assert result.status_code == expected, result.text
            return result.json()

        command("arm")
        doc = command("roll")["session"]
        take_id = doc["active_take"]
        try:
            command("hold", "a")
            time.sleep(3)
            # Exact unique test-take URL prevents touching another production.
            targets = {f"/{take_id}/{cam}" for cam in ("abc" if all_cameras else "a")}
            processes = subprocess.check_output(["ps", "-eo", "pid,command"], text=True)
            candidates = [int(line.split(None, 1)[0]) for line in processes.splitlines()
                          if "ffmpeg -nostdin" in line and any(line.rstrip().endswith(target) for target in targets)]
            assert len(candidates) == len(targets), candidates
            # Simulate an abrupt camera crash, not FFmpeg's potentially blocking
            # graceful RTSP teardown. This PID belongs only to the test take.
            for pid in candidates:
                os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                doc = client.get(route).json()
                if (all_cameras and doc["state"] == "READY") or (not all_cameras and doc["cameras"][0]["state"] == "OFFLINE"):
                    break
                time.sleep(.25)
            if all_cameras:
                assert doc["state"] == "READY", doc["state"]
                take = doc["takes"][-1]
                assert take["state"] == "PARTIAL" and not take["recordings_verified"]
                assert take["lost_cameras"] == list("abc")
                assert not any(take["recording_coverage"].values())
                events = client.get(route+"/events").json()
                assert any(e["kind"] == "take.stopping" and e["payload"]["reason"] == "All camera streams unavailable" for e in events)
                Path("artifacts/all-camera-failure-smoke.json").write_text(json.dumps({"session_id":doc["id"],"take":take,"events":events},indent=2))
                print(json.dumps({"status":"passed","all_cameras_lost":True,"automatically_stopped":True,"state":take["state"]}))
                return
            assert doc["state"] == "RECORDING", doc["state"]
            assert doc["cameras"][0]["state"] == "OFFLINE", doc["cameras"]
            assert doc["selected_camera"] == "c" and doc["hold"] is False
            rejected = command("switch", "a", expected=409)
            assert "unavailable" in rejected["detail"]
            time.sleep(2)
            doc = command("cut")["session"]
            take = doc["takes"][-1]
            assert take["state"] == "PARTIAL" and take["recordings_verified"] is False
            assert take["recording_coverage"] == {"a": False, "b": True, "c": True}, take["recording_coverage"]
            assert take["lost_cameras"] == ["a"]
            assert any(item.get("source") == "safety-fallback" for item in take["decisions"])
            events = client.get(route+"/events").json()
            Path("artifacts/camera-failure-smoke.json").write_text(json.dumps({"session_id": doc["id"], "take": take, "events": events}, indent=2))
            print(json.dumps({"status": "passed", "fallback": "c", "manual_hold_released_for_unavailable_camera": True,
                "dead_camera_rejected": True, "recording_coverage": take["recording_coverage"]}))
        finally:
            if client.get(route).json()["state"] == "RECORDING":
                command("cut")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-cameras", action="store_true")
    main(parser.parse_args().all_cameras)
