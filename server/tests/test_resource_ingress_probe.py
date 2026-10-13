import json

from test_e2e import MOCK_API, SCRIPT, lupa_mod


def runtime():
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute('''
        app=nil; probeTime=1; probeValue="first"; readCount=0
        os.clock=function() return probeTime end
        resolveutil={loadfile=function(path)
            assert(path=="tnj_tf3_ai_bridge::/tf3_mcp_bridge/ingress_probe.lua")
            readCount=readCount+1
            return function() return probeValue end
        end}
    ''')
    logs = []
    lua.globals().debugPrint = logs.append
    source = SCRIPT.read_text(encoding="utf-8")
    assert "local ENABLE_RESOURCE_INGRESS_PROBE = false" in source
    script = lua.execute(source.replace("local ENABLE_RESOURCE_INGRESS_PROBE = false",
                                        "local ENABLE_RESOURCE_INGRESS_PROBE = true", 1))
    return lua, logs, lambda: script["guiUpdate"](None, None, None)


def records(logs):
    return [json.loads(line.split("[TNJ_INGRESS_PROBE_V1]", 1)[1])
            for line in logs if "[TNJ_INGRESS_PROBE_V1]" in line]


def test_changed_payload_without_ui_and_bounded_polling():
    lua, logs, tick = runtime()
    tick(); tick()
    assert lua.globals().readCount == 1
    lua.execute('probeTime=2; probeValue="second"')
    tick()
    assert [r["value"] for r in records(logs)] == ["first", "second"]
    assert len({r["session"] for r in records(logs)}) == 1
    lua.execute('probeTime=123')
    tick(); tick()
    assert records(logs)[-1]["status"] == "ended"
    assert lua.globals().readCount == 2
    assert len(lua.globals().sentCommands) == 0


def test_invalid_payload_stops_without_dispatch_or_retry():
    lua, logs, tick = runtime()
    lua.execute('probeValue={cmd="commit_facility"}')
    tick()
    lua.execute('probeTime=3; probeValue="valid"')
    tick()
    assert len(records(logs)) == 1
    assert records(logs)[0]["status"] == "error"
    assert lua.globals().readCount == 1
    assert len(lua.globals().sentCommands) == 0
