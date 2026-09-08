"""Google STT + ADK voice intent changes actual production, not a simulated response."""
import json
import uuid
from pathlib import Path

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000",timeout=40) as client:
        result = client.post("/api/sessions").json()
        doc = result["session"]
        client.headers["Authorization"] = f"Bearer {result['token']}"
        route = f"/api/sessions/{doc['id']}"
        client.post(route+"/commands",json={"id":uuid.uuid4().hex,"kind":"arm","expected_revision":doc["revision"]}).raise_for_status()
        evidence = []
        for name in ("roll","hold","wide","cut"):
            current = client.get(route).json()
            body = {"id":uuid.uuid4().hex,"take_id":current["active_take"] or ""}
            files = {"audio":(name+".wav",Path(f"data/voice-fixtures/{name}.wav").read_bytes(),"audio/wav")}
            response = client.post(route+"/voice",data=body,files=files)
            response.raise_for_status()
            doc = response.json()["session"]
            repeat = client.post(route+"/voice",data=body,files=files)
            assert repeat.status_code==200 and repeat.json()==response.json()
            if name=="roll": assert doc["state"]=="RECORDING"
            if name=="hold": assert doc["hold"] and doc["selected_camera"]=="b"
            if name=="wide": assert doc["selected_camera"]=="c"
            if name=="cut": assert doc["state"]=="READY" and doc["takes"][-1]["recordings_verified"]
            evidence.append(doc["voice"])
            print(json.dumps(doc["voice"]),flush=True)
        Path("artifacts/voice-smoke.json").write_text(json.dumps({"status":"passed","session_id":doc["id"],"commands":evidence},indent=2))


if __name__ == "__main__":
    main()
