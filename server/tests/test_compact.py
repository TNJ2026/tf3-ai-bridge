"""Tool-output compaction keeps decisions intact while dropping bulk lists."""
import json

from tf3_mcp.compact import compact_ping, compact_road, compact_status, path_summary


def test_path_summary_reports_steepest_leg():
    path = [{"x": 0, "y": 0, "z": 1}, {"x": 30, "y": 40, "z": 3.5}, {"x": 30, "y": 90, "z": 9.5}, {"x": 30, "y": 140, "z": 9}]
    s = path_summary(path)
    assert s == {"pathPoints": 4, "minZ": 1, "maxZ": 9.5, "maxGradePercent": 12.0, "maxGradeAt": {"x": 30, "y": 90}}


def test_compact_preview_drops_path_but_keeps_decision_fields():
    path = [{"x": i * 50.0, "y": 0, "z": 1 + (i == 3) * 10} for i in range(100)]
    preview = {"ok": True, "buildable": True, "cost": 1059182, "messages": ["坡度过大"], "collisions": [],
               "length": 4645, "points": [{"node": 65615}], "path": path}
    out = compact_road(preview)
    assert "path" not in out and out["pathPoints"] == 100 and out["maxGradePercent"] == 20.0
    for key in ("ok", "buildable", "cost", "messages", "collisions", "length", "points"):
        assert out[key] == preview[key]
    assert len(json.dumps(out)) < len(json.dumps(preview)) / 5


def test_compact_build_summarizes_nodes_and_duplicate_edges():
    edges = list(range(82975, 83075))
    built = {"built": True, "verified": True, "complete": True, "edges": edges,
             "nodes": list(range(82857, 82956)),
             "connections": {"verified": True, "edges": edges, "junctions": [{"node": 65615, "verified": True}]}}
    out = compact_road(built)
    assert out["edges"] == edges
    assert out["nodes"] == {"count": 99, "first": 82857, "last": 82955}
    assert out["connections"] == {"verified": True, "junctions": [{"node": 65615, "verified": True}]}
    assert compact_road({"nodes": [1, 2], "edges": [3]})["nodes"] == [1, 2]  # short lists stay as is


def test_compact_status_and_ping_drop_probe():
    probe = {"state": "gui", "luaVersion": "Lua 5.2", "io": "nil", "bridgeVersion": "0.12.0"}
    status = {"connected": True, "heartbeatAgeSeconds": 0.3, "bridgeDir": "d:/x",
              "heartbeat": {"bridgeVersion": "0.12.0", "gameTime": 4896000, "paused": False, "tickCount": 7,
                            "requestsHandled": 9, "updateCount": 99, "clock": 1.0, "probe": probe}}
    assert compact_status(status) == {"connected": True, "heartbeatAgeSeconds": 0.3, "bridgeDir": "d:/x",
                                      "bridgeVersion": "0.12.0", "gameTime": 4896000, "paused": False,
                                      "tickCount": 7, "requestsHandled": 9, "luaState": "gui"}
    assert compact_status({"connected": False, "reason": "no heartbeat"}) == {"connected": False, "reason": "no heartbeat"}
    assert compact_ping({"pong": True, "echo": "x", "probe": probe, "userdataFolder": "C:/u"}) == \
        {"pong": True, "echo": "x", "bridgeVersion": "0.12.0", "state": "gui"}
