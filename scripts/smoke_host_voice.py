"""Hosted voice API with owned Google-voiced WAVs; not a physical mic claim."""
import json
from pathlib import Path
import time
import uuid

import httpx


def main():
    state = json.loads(Path("data/hosting-browser-state.json").read_text())["origins"][0]
    credentials = json.loads(state["localStorage"][0]["value"])
    route = "/api/sessions/" + credentials["id"]
    with httpx.Client(base_url=state["origin"], headers={"Authorization": "Bearer "+credentials["token"]}, timeout=45) as client:
        def doc():
            response = client.get(route)
            response.raise_for_status()
            return response.json()
        def command(kind):
            response = client.post(route+"/commands", json={"id": uuid.uuid4().hex, "kind": kind, "expected_revision": doc()["revision"]})
            response.raise_for_status()
        command("auto_off")
        if doc()["state"] != "ARMED":
            command("arm")
        evidence = []
        try:
            for name in ("roll", "hold", "wide", "cut"):
                current = doc()
                payload = {"id": uuid.uuid4().hex, "take_id": current["active_take"] or ""}
                files = {"audio": (name+".wav", Path(f"data/voice-fixtures/{name}.wav").read_bytes(), "audio/wav")}
                started = time.monotonic()
                response = client.post(route+"/voice", data=payload, files=files)
                response.raise_for_status()
                current = response.json()["session"]
                assert client.post(route+"/voice", data=payload, files=files).json() == response.json()
                if name == "roll": assert current["state"] == "RECORDING"
                if name == "hold": assert current["hold"] and current["selected_camera"] == "b"
                if name == "wide": assert current["selected_camera"] == "c"
                if name == "cut": assert current["state"] == "READY"
                evidence.append({"action": name, "voice": current["voice"], "roundtrip_seconds": round(time.monotonic()-started, 3)})
        finally:
            if doc()["state"] == "RECORDING":
                command("cut")
        path = Path("artifacts/hosting/voice-api.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "passed", "scope": "Owned WAV upload to hosted voice API", "commands": evidence}, indent=2))
        print(json.dumps({"status": "passed", "commands": evidence, "report": str(path)}))


if __name__ == "__main__":
    main()
