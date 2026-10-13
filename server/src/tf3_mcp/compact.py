"""Shrink large tool results before they reach the agent; full data stays available on request."""
from __future__ import annotations

import math

HEARTBEAT_FIELDS = ("bridgeVersion", "gameTime", "paused", "tickCount", "requestsHandled", "lastError")


def path_summary(path: list[dict]) -> dict:
    """Point count, elevation range and steepest grade between consecutive sampled points."""
    out: dict = {"pathPoints": len(path)}
    zs = [p["z"] for p in path if p.get("z") is not None]
    if zs:
        out["minZ"], out["maxZ"] = min(zs), max(zs)
    steepest, at = 0.0, None
    for a, b in zip(path, path[1:]):
        run = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
        if run > 0 and a.get("z") is not None and b.get("z") is not None:
            grade = abs(b["z"] - a["z"]) / run
            if grade > steepest:
                steepest, at = grade, {"x": b["x"], "y": b["y"]}
    out["maxGradePercent"] = round(steepest * 100, 1)
    if at:
        out["maxGradeAt"] = at
    return out


def compact_road(result: dict) -> dict:
    """Replace the sampled path and per-node id lists of build_road results with summaries."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if isinstance(out.get("path"), list):
        out.update(path_summary(out.pop("path")))
    nodes = out.get("nodes")
    if isinstance(nodes, list) and len(nodes) > 4:
        out["nodes"] = {"count": len(nodes), "first": nodes[0], "last": nodes[-1]}
    conn = out.get("connections")
    if isinstance(conn, dict) and conn.get("edges") == out.get("edges"):
        out["connections"] = {k: v for k, v in conn.items() if k != "edges"}
    out["compacted"] = "path/node lists summarized; pass include_path=True for full data"
    return out


def compact_status(status: dict) -> dict:
    """Connection health without the Lua environment probe."""
    hb = status.get("heartbeat") or {}
    out = {k: status[k] for k in ("connected", "heartbeatAgeSeconds", "bridgeDir", "reason", "error") if k in status}
    snapshot = {k: hb[k] for k in HEARTBEAT_FIELDS if k in hb}
    probe = hb.get("probe") or {}
    if "state" in probe:
        snapshot["luaState"] = probe["state"]
    if status.get("connected"):
        out.update(snapshot)
    elif snapshot:
        # A disconnected heartbeat describes the old session, not the live map.
        out["lastKnown"] = snapshot
        out.setdefault("reason", "heartbeat is stale; lastKnown is historical, not current game state")
    return out


def compact_ping(result: dict) -> dict:
    if not isinstance(result, dict):
        return result
    out = {k: v for k, v in result.items() if k not in ("probe", "userdataFolder")}
    probe = result.get("probe") or {}
    for key in ("bridgeVersion", "state"):
        if key in probe:
            out[key] = probe[key]
    return out
