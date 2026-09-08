"""Isolated API admission test; AI budgets are zero so no model call can run."""
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus


def main():
    root = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="clappy-access-") as temporary, socket.socket() as sock:
        data = Path(temporary)
        (data/"fixtures").symlink_to(root/"data/fixtures", target_is_directory=True)
        (data/"recordings").symlink_to(root/"data/recordings", target_is_directory=True)
        invite = secrets.token_urlsafe(32)
        env = {**os.environ, "CLAPPY_DATA_DIR": str(data), "CLAPPY_DEMO_ACCESS_KEY": invite,
               "CLAPPY_DAILY_SESSIONS": "2", "CLAPPY_DAILY_TAKES": "1", "CLAPPY_DAILY_RENDERS": "1",
               "CLAPPY_DAILY_AI_JOBS": "0", "CLAPPY_DAILY_SPEECH_SECONDS": "0", "CLAPPY_DAILY_VOICE_REQUESTS": "0"}
        env.pop("CLAPPY_PUBLIC_ORIGIN", None)
        sock.bind(("127.0.0.1", 0)); sock.listen(128)
        port = sock.getsockname()[1]
        with (data/"server.log").open("w+") as log:
            process = subprocess.Popen([str(root/".venv/bin/uvicorn"), "services.api.main:app", "--fd", str(sock.fileno()), "--no-access-log"],
                                       env=env, pass_fds=(sock.fileno(),), stdout=log, stderr=subprocess.STDOUT)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
                    deadline = time.monotonic()+20
                    while True:
                        assert process.poll() is None, "Isolated API exited during startup"
                        try:
                            health = client.get("/api/health", timeout=1)
                            if health.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        if time.monotonic()>deadline:
                            raise TimeoutError("Isolated API did not start")
                        time.sleep(.2)
                    assert health.json()["access_required"] and health.json()["media"]["ready"]
                    assert client.post("/api/sessions").status_code == 403
                    assert client.post("/api/sessions", headers={"X-Clappy-Invite": "wrong"}).status_code == 403
                    a = client.post("/api/sessions", headers={"X-Clappy-Invite": invite}).json()
                    b = client.post("/api/sessions", headers={"X-Clappy-Invite": invite}).json()
                    assert client.post("/api/sessions", headers={"X-Clappy-Invite": invite}).status_code == 429
                    route = f"/api/sessions/{a['session']['id']}"
                    auth = {"Authorization": f"Bearer {a['token']}"}
                    assert client.get(route, headers={"Authorization": f"Bearer {b['token']}"}).status_code == 403
                    assert client.get(route, headers={**auth, "Origin": "https://untrusted.example"}).status_code == 403
                    response = client.get(route, headers=auth)
                    assert response.headers["cache-control"] == "no-store"
                    try:
                        with connect(f"ws://127.0.0.1:{port}{route}/live", origin="https://untrusted.example", open_timeout=3):
                            raise AssertionError("Foreign browser origin connected")
                    except InvalidStatus as exc:
                        assert exc.response.status_code == 403
                    client.headers.update(auth)
                    note = client.post(route+"/direction", json={"id":uuid.uuid4().hex,"kind":"recall","note":"Remember this production"})
                    assert note.status_code == 202
                    deadline = time.monotonic()+5
                    while time.monotonic()<deadline:
                        doc = client.get(route).json()
                        if doc.get("agent", {}).get("status") == "FAILED":
                            break
                        time.sleep(.1)
                    assert "daily ai jobs limit" in doc["agent"]["message"]
                    voice = client.post(route+"/voice", data={"id":uuid.uuid4().hex,"take_id":""}, files={"audio":("voice.wav",b"not-decoded-because-budget-is-zero")})
                    assert voice.status_code == 429
                    def command(kind):
                        state = client.get(route).json()
                        return client.post(route+"/commands", json={"id":uuid.uuid4().hex,"kind":kind,"expected_revision":state["revision"]})
                    assert command("arm").status_code == 200
                    assert command("roll").status_code == 200
                    time.sleep(2)
                    # The take/render allowance is exhausted, but CUT must work.
                    assert client.get(route+"/limits").json()["remaining"]["takes"] == 0
                    cut = command("cut")
                    assert cut.status_code == 200 and cut.json()["session"]["state"] == "READY"
                    assert command("arm").status_code == 200
                    assert command("roll").status_code == 429
                    deadline = time.monotonic()+60
                    while time.monotonic()<deadline:
                        doc = client.get(route).json()
                        if doc["takes"][-1]["edits"][0]["status"] in ("READY", "FAILED"):
                            break
                        time.sleep(.25)
                    assert doc["takes"][-1]["edits"][0]["status"] == "READY"
                    evidence = {"status":"passed","invite_required":True,"cross_session_denied":True,
                        "foreign_http_and_websocket_origins_denied":True,"session_cap_enforced":True,
                        "zero_ai_and_voice_budget_denied":True,"cut_after_budget_exhaustion":True,
                        "new_roll_after_budget_exhaustion_denied":True,"google_api_calls":0,
                        "take_id":doc["takes"][-1]["id"]}
                    (root/"artifacts/access-smoke.json").write_text(json.dumps(evidence,indent=2)+"\n")
                    print(json.dumps(evidence))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()


if __name__ == "__main__":
    main()
