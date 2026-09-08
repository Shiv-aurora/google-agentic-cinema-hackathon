"""Actual RTSP audio → Google STT → ADK/MCP shots, with a manual hold."""
import json
import time
import uuid
from pathlib import Path

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        result = client.post("/api/sessions").json()
        doc = result["session"]
        client.headers["Authorization"] = f"Bearer {result['token']}"
        route = f"/api/sessions/{doc['id']}"
        response = client.put(route+"/scene", json={"title": doc["title"], "script": doc["script"], "source_set": "last-train-v1"})
        response.raise_for_status()
        def command(kind, camera=None):
            current = client.get(route).json()
            response = client.post(route+"/commands",json={"id":uuid.uuid4().hex,"kind":kind,"camera":camera,"expected_revision":current["revision"]})
            response.raise_for_status()
            return response.json()["session"]
        command("auto_on")
        command("arm")
        doc = command("roll")
        start, last, held, hold_at, saw_end = time.monotonic(), -1, False, None, None
        while time.monotonic()-start < 44:
            doc = client.get(route).json()
            performance = doc.get("performance", {})
            if performance.get("status") == "FAILED":
                command("cut")
                raise RuntimeError(performance)
            line = performance.get("line", {}).get("id", -1)
            if line != last:
                print(json.dumps({"recognized_line":line,"program":doc["selected_camera"],"note":doc["note"]}),flush=True)
                last = line
            if line >= 2 and not held:
                command("hold", "c")
                held, hold_at = True, time.monotonic()
            if hold_at:
                assert doc["selected_camera"] == "c" or time.monotonic()-hold_at < .6
                if time.monotonic()-hold_at > 3:
                    command("release")
                    hold_at = None
            if line == 5:
                saw_end = saw_end or time.monotonic()
                if time.monotonic()-saw_end > 5:
                    break
            time.sleep(.4)
        doc = command("cut")
        take = doc["takes"][-1]
        history = client.get(route+"/events").json()
        recognized = {e["payload"]["line"]["id"] for e in history if e["kind"] == "performance.line"}
        applied = [e for e in history if e["kind"] == "agent.live.applied"]
        assert recognized == set(range(6)), recognized
        assert len(applied) >= 3, [(e["kind"], e["payload"].get("error")) for e in history]
        assert any(d.get("source") == "gemini" for d in take["decisions"]), take["decisions"]
        assert held and take["recordings_verified"]
        assert all(any(m["type"] == "mcp.response" for m in e["payload"]["mcp"]) for e in applied)
        Path("artifacts/live-director-smoke.json").write_text(json.dumps({"session_id":doc["id"],"take":take,"events":history},indent=2))
        print(json.dumps({"status":"passed","recognized_lines":len(recognized),"memory_backed_live_decisions":len(applied),"manual_hold":True,"duration":take["duration"]}))


if __name__ == "__main__":
    main()
