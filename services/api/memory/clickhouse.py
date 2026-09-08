"""Durable outbox delivery and server-enforced session-only analytical access."""
import asyncio
import json
import os
import re
import secrets
import sys
from pathlib import Path

import clickhouse_connect
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters


class ProductionMemory:
    def __init__(self, store):
        self.store = store
        self.lock = asyncio.Lock()
        self.ready = False
        self.error = "ClickHouse has not been checked"
        self.initialized = False
        self.store.db.execute("CREATE TABLE IF NOT EXISTS memory_users(session_id TEXT PRIMARY KEY, password TEXT NOT NULL)")
        self.store.db.commit()

    def client(self, **overrides):
        return clickhouse_connect.get_client(**{
            "host": os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
            "port": int(os.getenv("CLICKHOUSE_PORT", "8123")),
            "username": os.getenv("CLICKHOUSE_USERNAME", "clappy"),
            "password": os.getenv("CLICKHOUSE_PASSWORD", "clappy-local-only"),
            "database": "clappy", "secure": os.getenv("CLICKHOUSE_SECURE", "false") == "true",
            "connect_timeout": 3, "send_receive_timeout": 10, **overrides,
        })

    def initialize(self):
        with self.client() as client:
            client.command("""CREATE TABLE IF NOT EXISTS clappy.production_events (
                seq UInt64, id String, session_id String, kind LowCardinality(String),
                occurred Float64, payload String, schema_version UInt8
                ) ENGINE=ReplacingMergeTree ORDER BY (session_id, id)""")
        self.initialized = True

    async def flush(self):
        async with self.lock:
            try:
                if not self.initialized:
                    await asyncio.to_thread(self.initialize)
                rows = self.store.db.execute("SELECT seq,id,session_id,kind,timestamp,payload FROM events WHERE exported=0 ORDER BY seq LIMIT 500").fetchall()
                if rows:
                    values = []
                    for row in rows:
                        value = list(row) + [1]
                        payload = json.loads(row["payload"])
                        if "mcp" in payload:
                            # Keep full MCP evidence in SQLite; don't recursively
                            # feed earlier tool-result transcripts back to Gemini.
                            payload["mcp_message_count"] = len(payload.pop("mcp", []))
                            value[5] = json.dumps(payload)
                        values.append(value)
                    def insert():
                        with self.client() as client:
                            client.insert("production_events", values,
                                column_names=["seq", "id", "session_id", "kind", "occurred", "payload", "schema_version"])
                    await asyncio.to_thread(insert)
                    # A crash before this commit may redeliver IDs. Readers use FINAL.
                    with self.store.db:
                        self.store.db.executemany("UPDATE events SET exported=1 WHERE id=?", [(row["id"],) for row in rows])
                else:
                    def ping():
                        with self.client() as client:
                            client.query("SELECT 1")
                    await asyncio.to_thread(ping)
                self.ready, self.error = True, None
                return len(rows)
            except Exception as exc:
                self.ready, self.error = False, str(exc)
                raise

    def watermark(self, session_id):
        row = self.store.db.execute("SELECT COALESCE(MAX(CASE WHEN exported=1 THEN seq END),0) AS watermark, SUM(CASE WHEN exported=0 THEN 1 ELSE 0 END) AS pending FROM events WHERE session_id=?", (session_id,)).fetchone()
        return {"sequence": row["watermark"], "pending": row["pending"] or 0}

    async def provision_reader(self, session_id):
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("Invalid production ID")
        row = self.store.db.execute("SELECT password FROM memory_users WHERE session_id=?", (session_id,)).fetchone()
        password = row["password"] if row else secrets.token_hex(24)
        if not row:
            with self.store.db:
                self.store.db.execute("INSERT INTO memory_users VALUES(?,?)", (session_id, password))
        user, view = f"reader_{session_id}", f"memory_{session_id}"
        def setup():
            with self.client() as client:
                client.command(f"CREATE USER IF NOT EXISTS {user} IDENTIFIED WITH sha256_password BY '{password}'")
                # The driver reads ~1,400 system settings when connecting.
                client.command(f"ALTER USER {user} SETTINGS readonly=1, max_execution_time=5, max_result_rows=10000, max_memory_usage=100000000")
                # Raw clock batches remain in the audit store, but do not crowd
                # director notes and performance events out of creative recall.
                client.command(f"CREATE OR REPLACE VIEW clappy.{view} SQL SECURITY DEFINER AS SELECT seq,id,kind,occurred,payload FROM clappy.production_events FINAL WHERE session_id='{session_id}' AND kind NOT IN ('media.frame.read','monitor.applied','monitor.stalled')")
                client.command(f"GRANT SELECT ON clappy.{view} TO {user}")
        await asyncio.to_thread(setup)
        return user, password, view

    async def toolset(self, session_id):
        await self.flush()
        user, password, view = await self.provision_reader(session_id)
        # Official server uses MCP 2; ADK 2.8 currently uses MCP 1. Separate
        # Python environments keep their dependencies intact across stdio.
        executable = os.getenv("CLAPPY_MCP_PYTHON", str(Path(__file__).resolve().parents[3] / "infra/mcp-clickhouse/.venv/bin/python"))
        params = StdioServerParameters(command=executable, args=["-m", "mcp_clickhouse.main"], env={
            "CLICKHOUSE_HOST": os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
            "CLICKHOUSE_PORT": os.getenv("CLICKHOUSE_PORT", "8123"),
            "CLICKHOUSE_USER": user, "CLICKHOUSE_PASSWORD": password,
            "CLICKHOUSE_DATABASE": "clappy", "CLICKHOUSE_SECURE": os.getenv("CLICKHOUSE_SECURE", "false"),
            "CLICKHOUSE_ALLOW_WRITE_ACCESS": "false", "CLICKHOUSE_MCP_QUERY_TIMEOUT": "8",
            "CLICKHOUSE_CONNECT_TIMEOUT": "3", "CLICKHOUSE_SEND_RECEIVE_TIMEOUT": "10",
            "FASTMCP_CHECK_FOR_UPDATES": "off", "FASTMCP_SHOW_SERVER_BANNER": "false",
        })
        return McpToolset(connection_params=StdioConnectionParams(server_params=params, timeout=15),
                          tool_filter=["run_query"]), view

    async def run(self):
        while True:
            try:
                await self.flush()
            except Exception:
                pass  # Expose failure in health; manual production remains available.
            await asyncio.sleep(2)
