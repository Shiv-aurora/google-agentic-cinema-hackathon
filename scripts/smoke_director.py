"""One bounded real Google ADK request which must recall a persisted note via MCP."""
import asyncio
import json
import tempfile
from pathlib import Path

from services.api.agent.director import Director
from services.api.memory.clickhouse import ProductionMemory
from services.api.store import Store


async def main():
    with tempfile.TemporaryDirectory(prefix="clappy-director-") as temp:
        path = Path(temp) / "test.sqlite"
        store = Store(path)
        doc, _ = store.create()
        store.save(doc, "director.note", {"note": "Bella should carry the scene. Hold her reaction when Tom mentions the letter."})
        store.db.close()
        # Reconstruct after restart; the prompt does NOT contain the note.
        store = Store(path)
        director = Director(ProductionMemory(store))
        result = await director.ask(store.get(doc["id"]), "What was my previous direction about Bella? Be specific.")
        assert "Bella" in result["response"] and "letter" in result["response"].lower(), result["response"]
        assert any(e["type"] == "mcp.response" and not e["result"].get("isError") for e in result["mcp"])
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/director-smoke.json").write_text(json.dumps(result, indent=2))
        print(json.dumps({"status": "passed", "model": result["model"], "response": result["response"],
                          "mcp_messages": len(result["mcp"]), "elapsed": result["elapsed"]}))


if __name__ == "__main__":
    asyncio.run(main())
