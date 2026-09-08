"""Verify hosted admission and create private browser state for a test production."""
import json
import os
from pathlib import Path

import httpx


def main():
    access = json.loads(Path("data/hosting-access.json").read_text())
    origin = access["origin"]
    with httpx.Client(base_url=origin, timeout=30) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        assert health.json()["access_required"]
        assert client.post("/api/sessions").status_code == 403
        assert client.post("/api/sessions", headers={"X-Clappy-Invite": "invalid-test-invite"}).status_code == 403
        response = client.post("/api/sessions", headers={"X-Clappy-Invite": access["invitation"]})
        response.raise_for_status()
        result = response.json()
        credentials = {"id": result["session"]["id"], "token": result["token"]}
        state = {"cookies": [], "origins": [{"origin": origin, "localStorage": [
            {"name": "clappy-director-session", "value": json.dumps(credentials)}]}]}
        path = Path("data/hosting-browser-state.json")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(state, handle)
        print(json.dumps({"admission": "passed", "session_id": credentials["id"], "browser_state": str(path)}))


if __name__ == "__main__":
    main()
