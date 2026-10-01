"""Export complete native terrain, model instances and data-map cells to SQLite.

Requires permission to pause the simulation; always attempts to restore its original
speed. Uses the existing eval bridge and isolated read-only helpers, so no save reload
is needed. JSON payload columns contain zlib-compressed UTF-8 JSON (no truncation).
"""
import asyncio
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
import zlib

from tf3_mcp.bridge import Bridge

ROOT = Path(__file__).resolve().parents[1]


def pack(value):
    return zlib.compress(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def unpack(value):
    return json.loads(zlib.decompress(value))


def markers(value, counts, path=""):
    if isinstance(value, dict):
        if "_unavailable" in value or "_truncated" in value or value.get("...") == "truncated":
            raise ValueError(f"incomplete model instance at {path}")
        for field in value.get("_unavailableFields", []):
            counts[path + "." + field] += 1
        for key, item in value.items():
            if key != "_unavailableFields":
                markers(item, counts, path + "." + key)
    elif isinstance(value, list):
        for item in value:
            markers(item, counts, path + "[]")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-models", type=Path, help="retain completed terrain/layers and recapture all models")
    options = parser.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    destination = options.resume_models or ROOT / "exports" / ("map-" + stamp)
    if not options.resume_models:
        destination.mkdir(parents=True, exist_ok=False)
    else:
        assert (destination / "manifest.json").is_file() and (destination / "map.sqlite").is_file()
    db_path = destination / "map.sqlite"
    connection = sqlite3.connect(db_path)
    connection.executescript("""
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE terrain_tiles(x INTEGER,y INTEGER,entity_id INTEGER,side INTEGER,
        value_count INTEGER,values_zlib BLOB NOT NULL,probes_json TEXT,PRIMARY KEY(x,y));
      CREATE TABLE map_layers(name TEXT PRIMARY KEY,width INTEGER,height INTEGER);
      CREATE TABLE map_cells(layer TEXT,offset INTEGER,count INTEGER,values_zlib BLOB NOT NULL,
        PRIMARY KEY(layer,offset));
      CREATE TABLE model_entities(id INTEGER PRIMARY KEY,dynamic INTEGER,fat_count INTEGER,
        thin_count INTEGER,instances_zlib BLOB NOT NULL);
    """.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS "))
    report = {"status": "starting", "format": "SQLite; *_zlib columns are zlib-compressed UTF-8 JSON",
              "started": datetime.now(timezone.utc).isoformat(), "files": {}, "counts": {}}
    manifest = destination / "manifest.json"
    if options.resume_models:
        report = json.loads(manifest.read_text(encoding="utf-8"))
        report.setdefault("previousFailures", []).append(report.pop("error", "") or "model phase validation failed")
        report.pop("restoredSpeed", None)
        report.pop("restoreError", None)
        report["captureSessions"] = [{"sections": ["terrain", "map_layers"], "state": report["info"]["state"]}]
        assert connection.execute("SELECT count(*) FROM terrain_tiles").fetchone()[0] == report["info"]["terrain"]["totalTiles"]
        for layer in report["info"]["layers"]:
            actual = connection.execute("SELECT sum(count) FROM map_cells WHERE layer=?", (layer["name"],)).fetchone()[0]
            assert actual == layer["width"]*layer["height"], "cannot resume incomplete map layers"
        connection.execute("DELETE FROM model_entities")
        connection.commit()

    def save():
        temporary = manifest.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(manifest)

    bridge = Bridge(timeout=60)
    key = "export_" + uuid.uuid4().hex
    original_speed = None
    pause_requested = False
    initialized = False
    try:
        state = await bridge.call("get_game_state")
        original_speed = state["speedup"]
        report["originalSpeed"] = original_speed
        save()
        pause_requested = True
        await bridge.call("set_game_speed", {"speed": 0})
        paused = await bridge.call("get_game_state")
        assert paused["speedup"] == 0, "pause was not applied"
        source = (ROOT / "mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua").read_text(encoding="utf-8")
        helper = (ROOT / "scripts/export_map_data.lua").read_text(encoding="utf-8")
        initialize = ('local env=setmetatable({},{__index=_G}); local s=assert(load('
                      + json.dumps(source, ensure_ascii=False) + ',"=export_bridge","t",env))(); '
                      'local factory=assert(load(' + json.dumps(helper, ensure_ascii=False)
                      + ',"=export_helpers","t",env))(); scratch[' + json.dumps(key)
                      + ']=factory(s._internal); return true')
        await bridge.call("eval", {"code": initialize})
        initialized = True

        async def call(name, args=None):
            code = ('return scratch[' + json.dumps(key) + '].run(' + json.dumps(name)
                    + ',json.decode(' + json.dumps(json.dumps(args or {})) + '))')
            return json.loads(await bridge.call("eval", {"code": code}))

        info = await call("info")
        if options.resume_models:
            assert info["map"]["bounds"] == report["info"]["map"]["bounds"], "map changed"
            assert info["terrain"] == report["info"]["terrain"], "terrain layout changed"
            report["modelCaptureInfo"] = info
            report["captureSessions"].append({"sections": ["models"], "state": info["state"]})
        else:
            report["info"] = info
            report["captureSessions"] = [{"sections": ["terrain", "map_layers", "models"], "state": info["state"]}]
        report["status"] = "terrain"
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", ("model_capture_info" if options.resume_models else "info", json.dumps(info, ensure_ascii=False)))
        total = info["terrain"]["totalTiles"]
        count, values = connection.execute("SELECT count(*),coalesce(sum(value_count),0) FROM terrain_tiles").fetchone()
        for offset in range(total if options.resume_models else 0, total, 8):
            rows = await call("terrain", {"offset": offset, "count": 8})
            assert len(rows) == min(8, total-offset)
            for row in rows:
                assert len(row["values"]) == row["side"]**2
                assert all(isinstance(v, int) for v in row["values"])
                connection.execute("INSERT INTO terrain_tiles VALUES (?,?,?,?,?,?,?)", (
                    row["x"], row["y"], row["id"], row["side"], len(row["values"]),
                    pack(row["values"]), json.dumps(row["probes"])))
                count += 1
                values += len(row["values"])
            connection.commit()
            if count % 256 == 0 or count == total:
                report["counts"]["terrainTiles"] = count
                report["counts"]["terrainValuesWithSharedBorders"] = values
                save()
                print(f"Terrain {count}/{total} tiles, {values} raw heights", flush=True)
        assert count == total

        report["status"] = "map_layers"
        layer_counts = {}
        for layer in info["layers"]:
            name, width, height = layer["name"], layer["width"], layer["height"]
            connection.execute("INSERT OR IGNORE INTO map_layers VALUES (?,?,?)", (name, width, height))
            count = width*height if options.resume_models else 0
            for offset in range(count, width*height, 8192):
                result = await call("layer", {"name": name, "offset": offset, "count": 8192})
                assert result["offset"] == count and result["total"] == width*height
                data = result["values"]
                assert len(data) == min(8192, width*height-offset)
                connection.execute("INSERT INTO map_cells VALUES (?,?,?,?)", (name, offset, len(data), pack(data)))
                count += len(data)
                connection.commit()
            assert count == width*height
            layer_counts[name] = count
            report["counts"]["mapLayerCells"] = layer_counts
            save()
            print(f"Layer {name}: {count}/{width*height} cells", flush=True)

        report["status"] = "models"
        total = info["modelEntities"]
        entities = fat = thin = 0
        unavailable = Counter()
        for offset in range(0, total, 100):
            rows = await call("models", {"offset": offset, "count": 100})
            assert len(rows) == min(100, total-offset)
            for row in rows:
                markers(row, unavailable)
                for model in row["fat"]:
                    assert model.get("modelName"), f"missing model path: entity {row['id']} model {model.get('modelId')}"
                    assert len(model["transf"]["columns"]) == 4, f"incomplete matrix: entity {row['id']}"
                for model in row["thin"]:
                    assert model.get("modelName") and all(k in model for k in ("pos", "rot", "scale"))
                connection.execute("INSERT INTO model_entities VALUES (?,?,?,?,?)", (
                    row["id"], int(bool(row.get("dynamic"))), len(row["fat"]), len(row["thin"]), pack(row)))
                entities += 1
                fat += len(row["fat"])
                thin += len(row["thin"])
            connection.commit()
            if entities % 5000 == 0 or entities == total:
                report["counts"].update(modelEntities=entities, fatInstances=fat, thinInstances=thin)
                save()
                print(f"Models {entities}/{total} entities, {fat+thin} instances", flush=True)
        report["unavailableModelFields"] = dict(unavailable)
        end = await call("check")
        assert end["state"]["gameTime"] == info["state"]["gameTime"], "simulation time changed"
        assert end["modelEntities"] == entities
        report["pausedSimulationTimeVerified"] = True
        report["status"] = "verifying"
        save()
        # Verify the bytes actually saved, not only transport results.
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        verified = 0
        for side, n, blob in connection.execute("SELECT side,value_count,values_zlib FROM terrain_tiles"):
            data = unpack(blob)
            assert len(data) == n == side*side
            verified += 1
        assert verified == info["terrain"]["totalTiles"]
        for name, width, height in connection.execute("SELECT name,width,height FROM map_layers"):
            expected = 0
            for offset, n, blob in connection.execute("SELECT offset,count,values_zlib FROM map_cells WHERE layer=? ORDER BY offset", (name,)):
                assert offset == expected and len(unpack(blob)) == n
                expected += n
            assert expected == width*height
        verified = 0
        for nfat, nthin, blob in connection.execute("SELECT fat_count,thin_count,instances_zlib FROM model_entities"):
            row = unpack(blob)
            assert len(row["fat"]) == nfat and len(row["thin"]) == nthin
            verified += 1
        assert verified == entities
        report["storedPayloadsVerified"] = True
        report["status"] = "complete"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        raise
    finally:
        if initialized:
            try:
                await bridge.call("eval", {"code": 'scratch[' + json.dumps(key) + ']=nil; return true'})
            except Exception as error:
                report["cleanupError"] = str(error)
        if pause_requested and original_speed is not None:
            for attempt in range(3):
                try:
                    await bridge.call("set_game_speed", {"speed": original_speed})
                    actual = await bridge.call("get_game_state")
                    assert actual["speedup"] == original_speed
                    report["restoredSpeed"] = actual["speedup"]
                    break
                except Exception as error:
                    report["restoreError"] = str(error)
            if "restoredSpeed" in report:
                report.pop("restoreError", None)
        connection.close()
        report["finished"] = datetime.now(timezone.utc).isoformat()
        if db_path.exists():
            with db_path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            report["files"]["map.sqlite"] = {"bytes": db_path.stat().st_size, "sha256": digest}
        save()
        print(json.dumps({"status": report["status"], "directory": str(destination),
                          "counts": report["counts"], "restoredSpeed": report.get("restoredSpeed"),
                          "restoreError": report.get("restoreError")}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
