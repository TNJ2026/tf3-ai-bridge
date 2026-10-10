"""Fail-closed save/reload orchestration; caller must hold the shared batch lock.

The validator must freshly check the caller's map and object baseline. This helper
does not infer map identity or authorize a reload. A paused simulation is required.
"""
import asyncio
import json
import re
import time
from pathlib import Path


def map_identity(snapshot):
    """Compare complete map records independent of engine enumeration order."""
    result = dict(snapshot)
    for key in ("towns", "industries"):
        rows = snapshot[key]
        ids = [row["id"] for row in rows]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate {key} identifiers")
        result[key] = sorted(rows, key=lambda row: row["id"])
    return result


def signature(path):
    try:
        s = path.stat()
        return [s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino]
    except FileNotFoundError:
        return None


async def save_and_reload(bridge, slot, journal, validate, *, timeout=30, poll=.5):
    if not re.fullmatch(r"tf3_fullmap_auto_map_[0-9a-f]{16}", slot):
        raise ValueError("Expected the fixed automatic map slot")
    journal = Path(journal)
    # An existing attempt, including a failed/unknown attempt, is never replayed.
    with journal.open("x", encoding="utf8") as f:
        json.dump({"stage": "preflight", "slot": slot}, f)
    record = {"stage": "preflight", "slot": slot}

    def write():
        tmp = journal.with_suffix(journal.suffix + ".tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf8")
        tmp.replace(journal)

    async def check():
        if not bridge.heartbeat().get("connected"):
            raise RuntimeError("Bridge disconnected")
        if (await bridge.call("get_game_state"))["speedup"] != 0:
            raise RuntimeError("Save/reload validation requires paused simulation")
        await validate()

    try:
        await check()
        path = bridge.dir.parent / "save" / (slot + ".sav")
        before = signature(path)
        record.update(stage="save_submitted", before=before, path=str(path))
        write()
        await bridge.call("eval", {"code": f'app.saveGame("{slot}",function()end,false,true);return {{requested=true}}'})
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            current = signature(path)
            if current and current[0] > 0 and current != before and current == previous:
                break
            previous = current
            await asyncio.sleep(poll)
        else:
            raise RuntimeError("No newly written stable save; reload forbidden")
        record.update(stage="save_verified", signature=current)
        write()
        await check()
        if signature(path) != current:
            raise RuntimeError("Save changed after verification; reload forbidden")
        record["stage"] = "reload_submitted"
        write()
        result = await bridge.call("eval", {"code":
            "local id=api.type.SavegameId.new();id.path='';"
            f"id.saveGameName='{slot}';"
            "id.saveGameNamespace=app.SaveGameNamespace.getSavegame();"
            "app.loadGame(id,false,nil);return {requested=true}"})
        record.update(stage="reload_requested", result=result)
        write()
        return record
    except BaseException as exc:
        record.update(error=str(exc), stopped=True)
        write()
        raise
