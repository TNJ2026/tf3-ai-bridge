"""Audit live entity pagination and a full 64 m terrain grid without pausing the game.

Records coverage and unreadable fields, not an atomic savegame snapshot. Model/asset
pages contain instance counts; their individual models are not all expanded here.
"""
import asyncio
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from tf3_mcp.bridge import Bridge

ROOT = Path(__file__).resolve().parents[1]
KINDS = (
    "TOWN", "INDUSTRY", "CONSTRUCTION", "TOWN_BUILDING", "BASE_NODE", "BASE_EDGE",
    "STATION", "STATION_GROUP", "VEHICLE_DEPOT", "TRANSPORT_VEHICLE", "SIM_PERSON",
    "LINE", "WATER_MESH", "MODEL_INSTANCE_LIST", "ASSET_GROUP", "SIM_CARGO",
    "STOCK_LIST", "TERRAIN_TILE_BRUSH",
)


def inspect(value, counts, path=""):
    if isinstance(value, dict):
        for field in value.get("_unavailableFields", []):
            counts[f"unavailable:{path}.{field}"] += 1
        if "_unavailable" in value:
            counts[f"opaque:{path}"] += 1
        if "_truncated" in value or value.get("...") == "truncated":
            counts[f"truncated:{path}"] += 1
        for key, child in value.items():
            if key not in ("_unavailableFields", "_unavailable", "_truncated"):
                # Collapse numeric map keys so report size doesn't scale with cargo IDs.
                label = "[]" if str(key).isdigit() else "." + str(key)
                inspect(child, counts, path + label)
    elif isinstance(value, list):
        for child in value:
            inspect(child, counts, path + "[]")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="audit shifting live offsets instead of stable IDs")
    parser.add_argument("--isolated-load", action="store_true", help="validate saved handlers in a separate Lua environment")
    options = parser.parse_args()
    bridge = Bridge(timeout=30)
    key = "audit_" + uuid.uuid4().hex
    if options.isolated_load:
        source = (ROOT / "mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua").read_text(encoding="utf-8")
        await bridge.call("eval", {"code": 'scratch[' + json.dumps(key) + ']=assert(load('
                          + json.dumps(source, ensure_ascii=False)
                          + ',"=map_audit","t",setmetatable({},{__index=_G})))(); return true'})

    async def call(command, args):
        if not options.isolated_load:
            return await bridge.call(command, args)
        code = ('local s=scratch[' + json.dumps(key) + ']; return s._internal.json.encode('
                's._internal.commands[' + json.dumps(command) + '](json.decode('
                + json.dumps(json.dumps(args)) + ')))')
        return json.loads(await bridge.call("eval", {"code": code}))
    report = {"startedUTC": datetime.now(timezone.utc).isoformat(), "heartbeat": bridge.heartbeat(),
              "consistency": "live offsets" if options.live else "fixed IDs per kind, live fields",
              "handlers": "isolated saved source" if options.isolated_load else "active GUI",
              "entities": {}, "errors": {}}
    target = ROOT / ("map_coverage_audit.json" if options.live else "map_coverage_snapshot_audit.json")

    def save():
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    for kind in KINDS:
        seen, counts, totals = set(), Counter(), set()
        offset = duplicates = pages = missing = 0
        snapshot = None if options.live else "new"
        try:
            while True:
                args = {"kind": kind, "offset": offset,
                        "limit": 500 if kind in ("ASSET_GROUP", "MODEL_INSTANCE_LIST") else 100}
                if snapshot is not None:
                    args["snapshot"] = snapshot
                page = await call("list_map_entities", args)
                snapshot = page.get("snapshot")
                pages += 1
                totals.add(page["total"])
                for item in page["items"]:
                    duplicates += item["id"] in seen
                    seen.add(item["id"])
                    missing += bool(item.get("missing"))
                    inspect(item.get("components", {}), counts)
                if not page["hasMore"]:
                    break
                following = page["nextOffset"]
                if following <= offset or pages > 10000:
                    raise RuntimeError("pagination did not advance")
                offset = following
                if pages % 100 == 0:
                    print(f"{kind}: {pages} pages processed, {len(seen)} unique so far", flush=True)
            report["entities"][kind] = {
                "uniqueEntitiesRead": len(seen), "pages": pages, "duplicates": duplicates,
                "deletedOrChangedComponent": missing,
                "observedTotals": sorted(totals), "fieldIssues": dict(sorted(counts.items())),
                "matchesObservedTotal": len(totals) == 1 and len(seen) in totals and duplicates == 0,
                "detail": "instance counts only" if kind in ("ASSET_GROUP", "MODEL_INSTANCE_LIST") else "component fields",
            }
            print(f"{kind}: {len(seen)} unique, {pages} pages, {duplicates} duplicates, {sum(counts.values())} field markers", flush=True)
        except Exception as error:
            report["errors"][kind] = str(error)
            print(f"{kind}: ERROR {error}", flush=True)
        finally:
            if snapshot and snapshot != "new":
                try:
                    await call("release_map_snapshot", {"snapshot": snapshot})
                except Exception as error:
                    report["errors"][kind + ".release"] = str(error)
        save()

    try:
        offset = samples = water = 0
        low, high = float("inf"), float("-inf")
        while True:
            page = await call("get_terrain_grid", {"spacing": 64, "offset": offset, "limit": 1024})
            assert page["offset"] == samples
            assert len(page["heights"]) == len(page["water"])
            samples += len(page["heights"])
            water += sum(page["water"])
            low = min(low, min(page["heights"]))
            high = max(high, max(page["heights"]))
            if not page["hasMore"]:
                break
            offset = page["nextOffset"]
        assert samples == page["total"]
        report["terrain"] = {"spacing": 64, "samples": samples, "waterSamples": water,
                             "minHeight": low, "maxHeight": high,
                             "columns": page["columns"], "rows": page["rows"], "completeAtRequestedSpacing": True}
        print(f"Terrain: {samples} samples at 64 m spacing", flush=True)
    except Exception as error:
        report["errors"]["terrain"] = str(error)
    report["finishedUTC"] = datetime.now(timezone.utc).isoformat()
    if options.isolated_load:
        await bridge.call("eval", {"code": 'scratch[' + json.dumps(key) + ']=nil; return true'})
    save()
    print(f"Saved {target}; errors: {len(report['errors'])}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
