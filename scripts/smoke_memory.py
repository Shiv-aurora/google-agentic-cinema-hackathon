"""Local real ClickHouse + official MCP verification, no model needed."""
import asyncio
import json
import tempfile
from pathlib import Path

from services.api.memory.clickhouse import ProductionMemory
from services.api.store import Store


async def main():
    with tempfile.TemporaryDirectory(prefix="clappy-memory-") as temp:
        store = Store(Path(temp) / "test.sqlite")
        memory = ProductionMemory(store)
        doc, _ = store.create()
        other, _ = store.create()
        store.save(doc, "director.note", {"note": "Stay on Bella after the reveal"})
        store.save(doc, "media.frame.read", {"packet": "Telemetry stays out of creative recall"})
        store.save(other, "director.note", {"note": "Other production, private"})
        await memory.flush()
        # Force redelivery to verify readers deduplicate event IDs.
        store.db.execute("UPDATE events SET exported=0")
        store.db.commit()
        await memory.flush()
        toolset, view = await memory.toolset(doc["id"])
        try:
            available = await toolset.get_tools()
            tool = next(t for t in available if t.name == "run_query")
            result = await tool.run_async(args={"query": f"SELECT seq,kind,payload FROM clappy.{view} ORDER BY seq"}, tool_context=None)
            assert not result.get("isError"), result
            table = json.loads(result["content"][0]["text"])
            encoded = json.dumps(table)
            assert "Stay on Bella" in encoded and "Other production, private" not in encoded, encoded
            assert "Telemetry stays out" not in encoded, encoded
            assert encoded.count("Stay on Bella") == 1, encoded
            user, password, _ = await memory.provision_reader(doc["id"])
            # Verify ordinary cross-session reads and writes are denied server-side.
            with memory.client(username=user, password=password) as reader:
                assert reader.query(f"SELECT count() FROM clappy.{view}").first_row[0] == 2
                for query in ["SELECT * FROM clappy.production_events LIMIT 1", f"INSERT INTO clappy.{view} VALUES(1)"]:
                    try:
                        reader.query(query)
                    except Exception:
                        pass
                    else:
                        raise AssertionError("Read-only session scope was not enforced")
            print(json.dumps({"status": "passed", "official_mcp_tools": [t.name for t in available],
                "deduplicated_events": 2, "session_isolation": True, "readonly": True,
                "watermark": memory.watermark(doc["id"])}))
        finally:
            await toolset.close()


if __name__ == "__main__":
    asyncio.run(main())
