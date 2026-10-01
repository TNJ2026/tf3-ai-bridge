"""Read-only map inventory through the actual local MCP stdio server."""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    folder = Path("exports") / ("map_read_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    folder.mkdir(parents=True, exist_ok=False)
    results = {}
    params = StdioServerParameters(command=sys.executable, args=["-m", "tf3_mcp.server"], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            async def call(name, args=None):
                response = await session.call_tool(name, args or {})
                if response.is_error:
                    raise RuntimeError(f"{name}: {response.content}")
                value = response.structured_content
                if value is None:
                    value = json.loads("".join(c.text for c in response.content if c.type == "text"))
                return value
            for name in ("bridge_status", "ping", "get_game_state", "get_map_info", "list_facilities"):
                results[name] = await call(name)
                (folder / (name + ".json")).write_text(json.dumps(results[name], ensure_ascii=False, indent=2), encoding="utf-8")
                print(name, json.dumps(results[name], ensure_ascii=False)[:1600], flush=True)
                if name == "bridge_status" and not results[name].get("connected"):
                    raise RuntimeError("Bridge heartbeat is stale; stop inventory")
            for kind in ("TOWN", "INDUSTRY", "STATION_GROUP", "VEHICLE_DEPOT", "LINE", "TRANSPORT_VEHICLE", "BASE_EDGE"):
                offset, token, pages = 0, "new", []
                try:
                    while True:
                        page = await call("list_map_entities", dict(kind=kind, offset=offset, limit=500, snapshot=token))
                        token = page["snapshot"]
                        pages.append(page)
                        if not page["hasMore"]:
                            break
                        offset = page["nextOffset"]
                finally:
                    if token != "new":
                        await call("release_map_snapshot", {"snapshot": token})
                results[kind] = {"total": pages[0]["total"], "items": [item for p in pages for item in p["items"]]}
                (folder / (kind + ".json")).write_text(json.dumps(results[kind], ensure_ascii=False, indent=2), encoding="utf-8")
                print(kind, results[kind]["total"], flush=True)
            results["end_state"] = await call("get_game_state")
            summary = dict(start_state=results["get_game_state"], end_state=results["end_state"],
                           map=results["get_map_info"], facilities=results["list_facilities"],
                           counts={k: results[k]["total"] for k in ("TOWN", "INDUSTRY", "STATION_GROUP", "VEHICLE_DEPOT", "LINE", "TRANSPORT_VEHICLE", "BASE_EDGE")},
                           consistency="Read-only; simulation remains running. IDs fixed per entity kind, fields live. Not a full save or terrain export.")
            (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OUTPUT", folder.resolve(), flush=True)


asyncio.run(main())
