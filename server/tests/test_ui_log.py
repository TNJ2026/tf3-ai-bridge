import json

import pytest

from tf3_mcp.ui_log import UiLogRequests
from test_e2e import MOCK_API, SCRIPT, lupa_mod


@pytest.mark.parametrize("command,args", [
    ("list_towns", {"limit": True}), ("list_lines", {"limit": 0}),
    ("list_vehicles", {"limit": 501}), ("list_stations", {"mine_only": 1}),
    ("get_game_state", {"limit": 1}), ("list_depots", {"line": 400}),
    ("list_vehicle_models", {"year": 1.5}), ("list_vehicle_models", {"carrier": "BOGUS"}),
    ("list_vehicle_models", {"include_unavailable": "true"}),
])
def test_argument_rejection_on_both_sides(tmp_path, command, args):
    path = tmp_path / "stdout.txt"
    path.touch()
    with pytest.raises(ValueError, match="argument"):
        UiLogRequests().prepare(path, command, args)
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    output = []
    lua.globals().print = output.append
    handler = lua.execute(SCRIPT.read_text(encoding="utf-8"))["guiHandleEvent"]
    result = handler(None, None, None, "", "tnj_bridge_readonly", "tnj_bridge_readonly.request",
                     "e" * 32 + " " + command + " " + json.dumps(args))
    assert "argument" in result.lower()
    assert not output
    assert len(lua.globals().sentCommands) == 0


def test_parameterized_queries_and_large_payloads(tmp_path):
    path = tmp_path / "stdout.txt"
    path.touch()
    reader = UiLogRequests()
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute('''
      api.engine.terrain = {
        getBoundingBox=function() return {min={x=-100,y=-100},max={x=100,y=100}} end,
        getBaseResolution=function() return 4 end,
        getHighResolution=function() return 1 end,
        makeMapFromGame=function() return {towns={},industries={},climateId="temperate"} end,
      }
      components[500] = {[9]={carrier=0,state=1,line=400,noPath=false},[10]={player=2}}
    ''')
    output = []
    lua.globals().print = output.append
    handler = lua.execute(SCRIPT.read_text(encoding="utf-8"))["guiHandleEvent"]

    def query(command, args=None):
        ticket = reader.prepare(path, command, args)
        status = handler(None, None, None, "", "tnj_bridge_readonly", "tnj_bridge_readonly.request", ticket["input"])
        frame_count = len(output)
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(output) + "\n")
        output.clear()
        return reader.read(ticket["id"])["response"], status, frame_count

    assert query("list_towns", {"limit": 1})[0]["result"]["count"] == 1
    assert query("list_lines", {"mine_only": False})[0]["result"]["lines"][0]["id"] == 400
    assert query("list_vehicles", {"limit": 1})[0]["result"]["vehicles"][0]["line"] == 400
    assert query("list_stations", {"limit": 1})[0]["result"]["count"] == 1
    assert query("list_depots", {"mine_only": True})[0]["result"]["depots"][0]["id"] == 300
    models = query("list_vehicle_models", {"year": 1850, "carrier": "ROAD", "limit": 1})[0]
    assert models["result"]["models"][0]["model"] == "vehicle/bus/old_bus.mdl"
    assert query("get_finances")[0]["result"]["loan"] == 0
    assert query("get_map_info")[0]["result"]["width"] == 200
    lua.execute('components[400][1].name=string.rep("large",1000)')
    response, status, frames = query("list_lines", {"mine_only": False})
    assert response["result"]["lines"][0]["name"] == "large" * 1000
    assert frames > 1 and status == "Result logged"
    lua.execute('components[400][1].name=string.rep("large",14000)')
    response, status, frames = query("list_lines", {"mine_only": False})
    assert response["ok"] is False and response["error"] == "Response too large"
    assert status == "Error logged" and frames == 1
    assert len(lua.globals().sentCommands) == 0


def test_live_handler_protocol_and_duplicate_guard(tmp_path):
    path = tmp_path / "stdout.txt"
    path.write_text("old log\n")
    reader = UiLogRequests()
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    output = []
    lua.globals().print = lambda value: output.append(value)
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    handler = script["guiHandleEvent"]
    # Native event filtering also applies to existing, already-subscribed saves.
    state = lua.execute("""
        local s = {data={existing="preserved"}, subs={tf3_mcp_request=true}, calls=0}
        function s:get() return self.data end
        function s:set(v) self.data=v end
        function s:hasEventSubscriptions() return next(self.subs)~=nil end
        function s:subscribeToEvent(n) self.subs[n]=true; self.calls=self.calls+1 end
        return s
    """)
    script["update"](None, state, 0)
    assert state["subs"]["tnj_bridge_readonly.request"] is True
    assert state["data"]["existing"] == "preserved"
    calls = state["calls"]
    script["update"](None, state, 0)
    assert state["calls"] == calls
    output.clear()
    for command in ("get_game_state", "list_towns", "list_lines", "list_vehicles", "list_stations"):
        ticket = reader.prepare(path, command)
        assert reader.read(ticket["id"])["status"] == "pending"
        assert handler(None, None, None, "", "tnj_bridge_readonly", "tnj_bridge_readonly.request", ticket["input"]) == "Result logged"
        count = len(output)
        assert "Duplicate" in handler(None, None, None, "", "tnj_bridge_readonly", "tnj_bridge_readonly.request", ticket["input"])
        assert len(output) == count
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(output) + "\n")
        output.clear()
        response = reader.read(ticket["id"])["response"]
        assert response["ok"] is True
        if command == "list_towns":
            assert response["result"]["count"] == 2
        elif command == "get_game_state":
            assert response["result"]["gameTime"] == 123000
        else:
            assert "count" in response["result"]
    assert "not allowed" in handler(None, None, None, "", "tnj_bridge_readonly", "tnj_bridge_readonly.request", "f" * 32 + " bulldoze")


def test_parser_partial_unicode_and_duplicate(tmp_path):
    path = tmp_path / "log"
    path.write_text("")
    reader = UiLogRequests()
    ticket = reader.prepare(path, "list_towns")
    body = json.dumps({"id": ticket["id"], "cmd": "list_towns", "ok": True, "result": "中文"}, ensure_ascii=False).encode().hex()
    line = f'[TNJ_UI_READ_V1] id={ticket["id"]} part=1 total=1 hex={body}'
    path.write_text(line)
    assert reader.read(ticket["id"])["status"] == "pending"
    path.write_text(line + "\n")
    assert reader.read(ticket["id"])["response"]["result"] == "中文"
    path.write_text(line + "\n" + line + "\n")
    with pytest.raises(ValueError, match="Duplicate"):
        reader.read(ticket["id"])


def test_reject_mutation_unknown_and_truncation(tmp_path):
    path = tmp_path / "log"
    path.write_text("baseline\n")
    reader = UiLogRequests()
    with pytest.raises(ValueError):
        reader.prepare(path, "eval")
    with pytest.raises(ValueError):
        reader.read("unknown")
    ticket = reader.prepare(path, "get_game_state")
    path.write_text("")
    with pytest.raises(ValueError, match="truncated"):
        reader.read(ticket["id"])


def test_timeout_late_response_and_reload(tmp_path):
    path = tmp_path / "stdout.txt"
    path.write_text("baseline\n", encoding="utf-8")
    now = [0]
    reader = UiLogRequests(clock=lambda: now[0])
    ticket = reader.prepare(path, "list_towns")
    now[0] = 61
    assert reader.read(ticket["id"])["status"] == "timeout_unknown"
    body = json.dumps(dict(id=ticket["id"], cmd="list_towns", ok=True, result={})).encode().hex()
    with path.open("a", encoding="utf-8") as f:
        f.write(f'[TNJ_UI_READ_V1] id={ticket["id"]} part=1 total=1 hex={body}\n')
    assert reader.read(ticket["id"])["status"] == "received"
    with path.open("a", encoding="utf-8") as f:
        f.write("[MESSAGE] Game is ready\n")
    with pytest.raises(ValueError, match="reloaded"):
        reader.read(ticket["id"])


def test_log_replaced_in_place_and_chunk_assembly(tmp_path):
    path = tmp_path / "stdout.txt"
    path.write_text("baseline\n", encoding="utf-8")
    reader = UiLogRequests()
    ticket = reader.prepare(path, "list_lines")
    body = json.dumps(dict(id=ticket["id"], cmd="list_lines", ok=True, result={"name": "中文" * 100})).encode().hex()
    chunks = [body[i:i+1500] for i in range(0, len(body), 1500)]
    with path.open("a", encoding="utf-8") as f:
        for part in reversed(range(len(chunks))):
            f.write(f'[TNJ_UI_READ_V1] id={ticket["id"]} part={part+1} total={len(chunks)} hex={chunks[part]}\n')
    assert reader.read(ticket["id"])["response"]["result"]["name"] == "中文" * 100
    with path.open("r+b") as f:
        f.write(b"REPLACED")
    with pytest.raises(ValueError, match="rewritten"):
        reader.read(ticket["id"])


def test_mcp_stdio_ui_query_roundtrip(tmp_path):
    import asyncio
    import os
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    log = tmp_path / "crash_dump" / "stdout.txt"
    log.parent.mkdir()
    log.write_text("initial\n", encoding="utf-8")

    async def run():
        env = dict(os.environ, TF3_MCP_DIR=str(tmp_path / "tf3_mcp"))
        params = StdioServerParameters(command=sys.executable, args=["-m", "tf3_mcp.server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {"prepare_ui_read_request", "prepare_ui_build_request", "read_ui_query_result"} <= names
                build = await session.call_tool("prepare_ui_build_request", {
                    "command": "build_warehouse", "arguments": {"x": 700, "y": 740, "z": 2}})
                assert not build.is_error
                build_ticket = build.structured_content or json.loads(build.content[0].text)
                assert build_ticket["status"] == "prepared_not_sent"
                assert "build_warehouse" in build_ticket["input"]
                bad_build = await session.call_tool("prepare_ui_build_request", {
                    "command": "build_road", "arguments": {}})
                assert bad_build.is_error
                rejected = await session.call_tool("prepare_ui_read_request", {"command": "bulldoze"})
                assert rejected.is_error
                prepared = await session.call_tool("prepare_ui_read_request", {
                    "command": "list_lines", "arguments": {"limit": 10, "mine_only": False}})
                assert not prepared.is_error
                ticket = prepared.structured_content or json.loads(prepared.content[0].text)
                assert json.loads(ticket["input"].split(" ", 2)[2]) == {"limit": 10, "mine_only": False}
                pending = await session.call_tool("read_ui_query_result", {"request_id": ticket["id"]})
                assert (pending.structured_content or json.loads(pending.content[0].text))["status"] == "pending"
                payload = dict(id=ticket["id"], cmd="list_lines", ok=True, result={"count": 0, "lines": []})
                with log.open("a", encoding="utf-8") as f:
                    f.write(f'[TNJ_UI_READ_V1] id={ticket["id"]} part=1 total=1 hex={json.dumps(payload).encode().hex()}\n')
                received = await session.call_tool("read_ui_query_result", {"request_id": ticket["id"]})
                assert not received.is_error
                assert (received.structured_content or json.loads(received.content[0].text))["response"] == payload
                assert not list((tmp_path / "tf3_mcp").glob("request*"))
    asyncio.run(run())
