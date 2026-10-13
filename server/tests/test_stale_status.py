from tf3_mcp.compact import compact_status


def test_disconnected_status_does_not_expose_old_world_state_as_current():
    status = {
        "connected": False,
        "heartbeatAgeSeconds": 1200,
        "heartbeat": {
            "gameTime": 13407800,
            "paused": False,
            "bridgeVersion": "0.12.9",
            "probe": {"state": "gui", "large": "omitted"},
        },
    }
    result = compact_status(status)
    assert "paused" not in result
    assert "gameTime" not in result
    assert "bridgeVersion" not in result
    assert result["lastKnown"] == {
        "gameTime": 13407800, "paused": False,
        "bridgeVersion": "0.12.9", "luaState": "gui",
    }
    assert "historical" in result["reason"]
    assert "lastKnown" not in status  # Do not rewrite the raw evidence.


def test_disconnected_status_keeps_specific_diagnostic():
    result = compact_status({
        "connected": False, "reason": "transport unavailable",
        "heartbeat": {"paused": True},
    })
    assert result["reason"] == "transport unavailable"
    assert result["lastKnown"]["paused"] is True


def test_no_heartbeat_has_no_invented_snapshot():
    assert compact_status({"connected": False, "reason": "no heartbeat"}) == {
        "connected": False, "reason": "no heartbeat",
    }
