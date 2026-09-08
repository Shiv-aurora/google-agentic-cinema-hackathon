"""Verify normal media credentials and denied access on the local demo rig."""
import json
import subprocess
import uuid
from pathlib import Path

import httpx


def read_frame(url):
    try:
        result = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-rtsp_transport", "tcp", "-i", url,
            "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        raise RuntimeError("The bounded local media read timed out") from None
    return result.returncode, b"401" in result.stderr


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        created = client.post("/api/sessions").json()
        route = f"/api/sessions/{created['session']['id']}"
        client.headers["Authorization"] = f"Bearer {created['token']}"
        def command(kind):
            doc = client.get(route).json()
            result = client.post(route+"/commands", json={"id":uuid.uuid4().hex,"kind":kind,"expected_revision":doc["revision"]})
            result.raise_for_status()
            return result.json()["session"]
        command("arm")
        doc = command("roll")
        take_id = doc["active_take"]
        ticket_url = route+f"/media-ticket/{take_id}/a"
        try:
            with httpx.Client(timeout=5) as anonymous:
                assert anonymous.get("http://127.0.0.1:9997/v3/paths/list").status_code == 401
                assert anonymous.get("http://127.0.0.1:8000"+ticket_url).status_code == 403
            ticket = client.get(ticket_url).json()
            base = f"rtsp://{ticket['user']}:{ticket['pass']}@127.0.0.1:8554"
            assert read_frame(f"{base}/{take_id}/a")[0] == 0, "Scoped camera read failed"
            assert read_frame(f"{base}/{take_id}/b")[1], "Camera A credential was not denied for camera B"
            assert read_frame(f"rtsp://127.0.0.1:8554/{take_id}/a")[1], "Anonymous camera read was not denied"
            with httpx.Client(timeout=5, auth=(ticket["user"],ticket["pass"])) as reader:
                assert reader.get("http://127.0.0.1:9997/v3/paths/list").status_code == 401
            state = client.get(route).json()
            assert ticket["pass"] not in json.dumps(state)
            assert ticket["pass"] not in client.get(route+"/events").text
            player = client.get(route+f"/player/{take_id}/a")
            assert player.status_code == 200 and ticket["pass"] not in player.text
            assert player.headers["referrer-policy"] == "no-referrer"
            command("cut")
            assert client.get(ticket_url).status_code == 404
            assert read_frame(f"{base}/{take_id}/a")[1], "Stopped-take credential was not revoked"
            report = {"status":"passed","take_id":take_id,"authenticated_read":True,
                "anonymous_read_denied":True,"cross_camera_read_denied":True,"reader_admin_denied":True,
                "ticket_requires_production_key":True,"no_credential_in_state_events_or_player_url":True,
                "credentials_revoked_after_cut":True}
            Path("artifacts/media-auth-smoke.json").write_text(json.dumps(report,indent=2)+"\n")
            print(json.dumps(report))
        finally:
            if client.get(route).json()["state"] == "RECORDING":
                command("cut")


if __name__ == "__main__":
    main()
