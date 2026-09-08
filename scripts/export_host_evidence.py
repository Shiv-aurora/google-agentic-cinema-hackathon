"""Export non-secret hosted smoke evidence and verify downloaded edit hashes."""
import hashlib
import json
from pathlib import Path

import httpx


def main():
    state = json.loads(Path("data/hosting-browser-state.json").read_text())
    origin = state["origins"][0]["origin"]
    credentials = json.loads(state["origins"][0]["localStorage"][0]["value"])
    with httpx.Client(base_url=origin, headers={"Authorization": "Bearer " + credentials["token"]}, timeout=45) as client:
        route = "/api/sessions/" + credentials["id"]
        response = client.get(route)
        response.raise_for_status()
        doc = response.json()
        events = client.get(route+"/events").json()
        summary = {"origin": origin, "session_id": doc["id"], "state": doc["state"], "takes": [],
                   "scope": "Hosted synthetic-source web demo; live timing remains estimated. No physical-device claim."}
        for take in doc["takes"]:
            summary["takes"].append({key: take.get(key) for key in
                ("id", "state", "duration", "source_set", "recordings_verified", "decisions")})
            item = summary["takes"][-1]
            item["transcript_count"] = len(take.get("transcripts", []))
            item["frame_read_batches"] = len(take.get("frame_read_batches", []))
            item["monitor_observations"] = len(take.get("monitor_observations", []))
            item["edits"] = [{key: edit.get(key) for key in ("id", "parent_id", "name", "status", "segments", "output")}
                             for edit in take.get("edits", [])]
        summary["ai_events"] = [{"kind": event["kind"], "timestamp": event["timestamp"],
            **{key: event["payload"].get(key) for key in ("take_id", "model", "project", "elapsed", "error", "reason", "response")},
            "official_mcp_response": any(row.get("type") == "mcp.response" and row.get("name") == "run_query"
                                         for row in event["payload"].get("mcp", []))}
            for event in events if event["kind"].startswith("agent.")]
        directory = Path("artifacts/hosting")
        directory.mkdir(parents=True, exist_ok=True)
        paired = next((take for take in reversed(doc["takes"]) if len(take.get("edits", [])) >= 2
                       and all(edit["status"] == "READY" for edit in take["edits"][:2])), None)
        summary["verified_downloads"] = []
        if paired:
            for edit in paired["edits"][:2]:
                video = client.get(f"{route}/edits/{edit['id']}/video")
                video.raise_for_status()
                digest = hashlib.sha256(video.content).hexdigest()
                assert digest == edit["output"]["sha256"]
                path = directory/f"{edit['id']}.mp4"
                path.write_bytes(video.content)
                manifest = client.get(f"{route}/edits/{edit['id']}/manifest")
                manifest.raise_for_status()
                (directory/f"{edit['id']}.json").write_text(json.dumps(manifest.json(), indent=2))
                summary["verified_downloads"].append({"edit_id": edit["id"], "sha256": digest, "bytes": len(video.content)})
        (directory/"smoke-summary.json").write_text(json.dumps(summary, indent=2)+"\n")
        print(json.dumps({"state": doc["state"], "take_count": len(doc["takes"]),
                          "verified_downloads": len(summary["verified_downloads"]), "report": str(directory/"smoke-summary.json")}))


if __name__ == "__main__":
    main()
