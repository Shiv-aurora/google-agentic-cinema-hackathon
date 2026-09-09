"""One-process transactional production state with a durable analytical outbox."""
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

CAMERAS = [
    {"id": "a", "name": "Camera A", "role": "Tom", "framing": "Close-up", "color": "#9bbcd5"},
    {"id": "b", "name": "Camera B", "role": "Bella", "framing": "Close-up", "color": "#dbbd91"},
    {"id": "c", "name": "Camera C", "role": "Wide", "framing": "Two-shot", "color": "#a9c7a5"},
]
SCRIPT = """INT. THE LAST TRAIN - NIGHT

TOM
You kept the ticket.

BELLA
I thought you might come back for it.

TOM
It's been three years.

BELLA
I know how long it's been.

TOM
The letter never reached me.

BELLA
I never sent it.

She holds his gaze. For the first time, he has no answer.
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, doc TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
            session_id TEXT NOT NULL, kind TEXT NOT NULL, timestamp REAL NOT NULL, payload TEXT NOT NULL,
            exported INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS commands(session_id TEXT, id TEXT, request TEXT NOT NULL, result TEXT,
            PRIMARY KEY(session_id,id));
        """)
        # Old process-owned publishers cannot be assumed alive after a restart.
        for row in self.db.execute("SELECT id,doc FROM sessions").fetchall():
            doc = json.loads(row["doc"])
            interrupted_edits = []
            for take in doc.get("takes", []):
                for edit in take.get("edits", []):
                    if edit.get("status") == "RENDERING":
                        edit.update(status="FAILED", error="Coordinator restarted during rendering. Sources and timeline are preserved; request another edit.")
                        interrupted_edits.append(edit["id"])
            if interrupted_edits:
                self.save(doc, "render.interrupted", {"edit_ids": interrupted_edits})
            if doc.get("agent", {}).get("status") == "THINKING":
                doc["agent"] = {"status": "FAILED", "message": "Coordinator restarted before this direction completed. Please retry."}
                self.save(doc, "agent.interrupted", {})
            if doc["state"] in ("ARMING", "ARMED", "STARTING", "RECORDING", "STOPPING"):
                for take in doc.get("takes", []):
                    if take.get("state") in ("STARTING", "RECORDING", "STOPPING"):
                        take["state"] = "INTERRUPTED"
                if doc.get("queued_direction", {}).get("status") in ("WAITING", "DEFERRED"):
                    doc["queued_direction"]["status"] = "EXPIRED"
                if doc.get("performance"):
                    doc["performance"]["status"] = "STOPPED"
                doc["hold"] = False
                doc["override_until"] = 0
                doc["control_epoch"] = doc.get("control_epoch", 0)+1
                doc["state"] = "INTERRUPTED"
                doc["error"] = "Coordinator restarted. Existing source media is preserved."
                for cam in doc["cameras"]:
                    cam["state"] = "OFFLINE"
                self.save(doc, "coordinator.recovered", {"previous_process": "interrupted"})
        with self.db:
            self.db.execute("UPDATE commands SET result=? WHERE result IS NULL", (json.dumps({"error": "Command interrupted by coordinator restart"}),))

    def create(self):
        token = secrets.token_urlsafe(32)
        session_id = uuid.uuid4().hex
        doc = {"id": session_id, "title": "The last train", "scene": "01", "state": "DRAFT", "revision": 0,
               "script": SCRIPT, "cameras": [{**cam, "state": "OFFLINE"} for cam in CAMERAS],
               "takes": [], "active_take": None, "selected_camera": "c", "hold": False,
               "policy": "Balanced", "note": "Your crew is ready to assemble.", "error": None}
        doc.update(source_set="charts", auto_enabled=False, control_epoch=0,
                   directing_preset="classic", live_direction="", direction_epoch=0)
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES(?,?,?)", (session_id, hashlib.sha256(token.encode()).hexdigest(), json.dumps(doc)))
        self.save(doc, "session.created", {"cameras": doc["cameras"], "script": doc["script"], "title": doc["title"]})
        return doc, token

    def authorize(self, session_id: str, token: str):
        row = self.db.execute("SELECT token_hash FROM sessions WHERE id=?", (session_id,)).fetchone()
        return bool(row and secrets.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest()))

    def get(self, session_id: str):
        row = self.db.execute("SELECT doc FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise KeyError(session_id)
        return json.loads(row["doc"])

    def save(self, doc: dict, kind: str, payload: dict):
        doc["revision"] += 1
        with self.db:
            self.db.execute("UPDATE sessions SET doc=? WHERE id=?", (json.dumps(doc), doc["id"]))
            self.db.execute("INSERT INTO events(id,session_id,kind,timestamp,payload) VALUES(?,?,?,?,?)",
                            (uuid.uuid4().hex, doc["id"], kind, time.time(), json.dumps(payload)))

    def events(self, session_id: str):
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in
                self.db.execute("SELECT seq,id,kind,timestamp,payload FROM events WHERE session_id=? ORDER BY seq DESC LIMIT 100", (session_id,))]

    def command(self, session_id: str, command_id: str, request: dict):
        encoded = json.dumps(request, sort_keys=True)
        row = self.db.execute("SELECT request,result FROM commands WHERE session_id=? AND id=?", (session_id, command_id)).fetchone()
        if row:
            if row["request"] != encoded:
                raise ValueError("Command ID was already used for a different request")
            return json.loads(row["result"]) if row["result"] else {"error": "Command is still in progress"}
        with self.db:
            self.db.execute("INSERT INTO commands VALUES(?,?,?,NULL)", (session_id, command_id, encoded))
        return None

    def complete(self, session_id: str, command_id: str, result: dict):
        with self.db:
            self.db.execute("UPDATE commands SET result=? WHERE session_id=? AND id=?", (json.dumps(result), session_id, command_id))
