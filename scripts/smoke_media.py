"""Exercise the real HTTP coordinator, MediaMTX and FFmpeg, not a mock hub."""
import argparse
import json
import time
import uuid
from pathlib import Path

import httpx


def main(base):
    with httpx.Client(base_url=base, timeout=30) as client:
        assert client.get("/api/health").json()["media"]["ready"]
        result = client.post("/api/sessions").json()
        session, token = result["session"], result["token"]
        client.headers["Authorization"] = f"Bearer {token}"
        route = f"/api/sessions/{session['id']}"
        def command(kind, camera=None):
            current = client.get(route).json()
            payload = {"id":uuid.uuid4().hex,"kind":kind,"camera":camera,"expected_revision":current["revision"]}
            response = client.post(route+"/commands",json=payload)
            response.raise_for_status()
            duplicate = client.post(route+"/commands",json=payload)
            assert duplicate.status_code == 200 and duplicate.json() == response.json()
            return response.json()["session"]
        command("arm")
        rolled = command("roll")
        assert all(c["state"] == "RECORDING" for c in rolled["cameras"])
        time.sleep(2)
        command("switch","a")
        time.sleep(2)
        command("hold","b")
        time.sleep(2)
        doc = command("cut")
        take = doc["takes"][-1]
        assert take["recordings_verified"], take["recordings"]
        assert len(doc["takes"]) == 1
        assert [s["camera"] for s in take["edits"][0]["segments"]] == ["c","a","b"]
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            doc = client.get(route).json()
            edit = doc["takes"][-1]["edits"][0]
            if edit["status"] == "FAILED":
                raise RuntimeError(edit)
            if edit["status"] == "READY":
                break
            time.sleep(.5)
        else:
            raise TimeoutError("Render did not finish")
        assert client.get(f"{route}/edits/{edit['id']}/video").status_code == 200
        assert client.get(f"{route}/edits/{edit['id']}/timeline").status_code == 200
        aligned = doc["takes"][-1]["alignment"]
        assert aligned["verified"], aligned
        assert all(cam["verified"] and cam["continuous"] for cam in aligned["cameras"].values())
        assert "live timing estimated" in edit["sync"]
        manifest = client.get(f"{route}/edits/{edit['id']}/manifest")
        manifest.raise_for_status()
        assert manifest.json()["alignment"]["verified"]
        assert manifest.json()["output"]["sha256"] == edit["output"]["sha256"]
        assert len(manifest.json()["timeline_sha256"]) == 64
        evidence = {"session_id":session["id"],"take":doc["takes"][-1],"events":client.get(route+"/events").json()}
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/media-smoke.json").write_text(json.dumps(evidence,indent=2)+"\n")
        print(json.dumps({"status":"passed","session_id":session["id"],"independent_recordings":3,"edit_id":edit["id"],"duration":take["duration"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base",default="http://127.0.0.1:8000")
    main(parser.parse_args().base)
