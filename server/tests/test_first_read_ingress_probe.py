import json

import pytest

from test_e2e import MOCK_API, SCRIPT, lupa_mod


def runtime(enabled=True):
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute('''
        app=nil; probeTime=1; readCount=0; marker="changed_one"; paths={}
        os.clock=function() return probeTime end
        resolveutil={loadfile=function(path)
            assert(not paths[path], "path read twice")
            paths[path]=true; readCount=readCount+1
            return function() return marker end
        end}
    ''')
    logs = []
    lua.globals().debugPrint = logs.append
    source = SCRIPT.read_text(encoding="utf-8")
    if enabled:
        source = source.replace("local ENABLE_FIRST_READ_PROBE = false",
                                "local ENABLE_FIRST_READ_PROBE = true", 1)
    script = lua.execute(source)
    return lua, logs, lambda: script["guiUpdate"](None, None, None)


def records(logs):
    return [json.loads(x.split("[TNJ_FIRST_READ_V1]", 1)[1])
            for x in logs if "[TNJ_FIRST_READ_V1]" in x]


def test_two_distinct_first_reads_after_ready_without_commands():
    lua, logs, tick = runtime()
    tick(); tick()
    assert lua.globals().readCount == 0
    lua.execute("probeTime=31")
    tick(); tick()
    lua.execute('probeTime=61; marker="changed_two"')
    tick(); tick()
    rows = records(logs)
    assert [(r["status"], r["slot"]) for r in rows] == [
        ("ready", 1), ("observed", 1), ("ready", 2), ("observed", 2)]
    assert [r["value"] for r in rows if r["status"] == "observed"] == ["changed_one", "changed_two"]
    assert len({r["session"] for r in rows}) == 1
    assert lua.globals().readCount == 2
    assert len(lua.globals().sentCommands) == 0


@pytest.mark.parametrize("failure", ["marker={}", "resolveutil.loadfile=function() error('failed') end", "probeTime=100"])
def test_failure_stops_without_retry(failure):
    lua, logs, tick = runtime()
    tick()
    lua.execute("probeTime=31; " + failure)
    tick(); tick()
    assert [r["status"] for r in records(logs)] == ["ready", "error"]
    assert lua.globals().readCount <= 1
    assert len(lua.globals().sentCommands) == 0


def test_release_does_not_poll():
    lua, logs, tick = runtime(False)
    tick()
    assert records(logs) == []
    assert lua.globals().readCount == 0
