"""Regression tests for native userdata, nested records and bounded map reads."""
import json

import pytest

from test_e2e import MOCK_API, SCRIPT, OpaqueGameValue, lupa_mod


@pytest.fixture
def runtime():
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    lua.execute("""
      local CT=api.type.ComponentType
      CT.TERRAIN=80; CT.TERRAIN_TILE_HEIGHTMAP=81; CT.TERRAIN_TILE_BRUSH=82
      CT.STOCK_LIST=83; CT.WATER_MESH=84; CT.SIM_CARGO=85
      api.type.Vec2f={new=function(x,y) return {x=x,y=y} end}
      api.type.Vec2i=api.type.Vec2f
      local layer={getSize=function() return {x=3,y=2} end,
        at=function(self,x,y) return x+10*y end}
      components[1][80]={baseResolution={x=4,y=4,z=0.05},offsetZ=-100,dataMaps={forest_mask=layer}}
      local vertices={}
      for i=1,4225 do vertices[i]=i*2 end
      components[600]={[81]={vertices=vertices}}
      api.engine.terrain={
        getBoundingBox=function() return {min={x=-256,y=-256},max={x=256,y=256}} end,
        getHeightAt=function(p) return p.x+10*p.y end,
        getBaseHeightAt=function(p) return p.x+10*p.y-5 end,
        isOnWater=function(p) return p.x<0 end,
        getHeightmapEntity=function(p) assert(p.x==-1 and p.y==-1); return 600 end
      }
      api.engine.forEachEntity=function(fn) for id in pairs(components) do fn(id) end end
      api.engine.system.riverSystem={getWaterMeshEntities=function(low,high)
        assert(low.x==-1 and low.y==-1 and high.x==0 and high.y==0)
        return {700}
      end}
      components[700]={[84]={vertices={{x=-1,y=2}},depths={3},indices={0},contours={}}}
    """)
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    def call(name, **args):
        result = script["_internal"]["commands"][name](lua.table_from(args, recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](result))
    return lua, call


def test_terrain_pages_have_exact_row_major_coordinates(runtime):
    _, call = runtime
    params = dict(x=-4, y=-4, spacing=4, columns=3, rows=2, limit=4)
    first = call("get_terrain_grid", **params)
    second = call("get_terrain_grid", **params, offset=first["nextOffset"])
    assert first["heights"] + second["heights"] == [-44, -40, -36, -4, 0, 4]
    assert first["water"] + second["water"] == [True, False, False, True, False, False]
    assert second["total"] == 6 and not second["hasMore"]
    base = call("get_terrain_grid", **params, mode="base")
    assert base["heights"] == [-49, -45, -41, -9]
    assert call("get_terrain_grid", **params, offset=99)["heights"] == []


@pytest.mark.parametrize("args", [
    {"spacing": 0}, {"spacing": float("nan")}, {"x": float("inf")},
    {"x": -257}, {"columns": 999}, {"rows": 0}, {"limit": 1025},
    {"offset": -1}, {"mode": "invalid"}, {"columns": 1.5},
])
def test_terrain_rejects_invalid_requests(runtime, args):
    _, call = runtime
    with pytest.raises(lupa_mod.LuaError):
        call("get_terrain_grid", **args)


def test_raw_tile_pages_are_not_truncated_at_2000(runtime):
    _, call = runtime
    tile = call("get_terrain_tile", tile_x=-1, tile_y=-1)
    assert tile["heightValueCount"] == 4225 and tile["brushAvailable"] is False
    assert tile["origin"] == {"x": -256, "y": -256}
    items, offset = [], 0
    while True:
        page = call("get_component_collection", id=600, component="TERRAIN_TILE_HEIGHTMAP", field="vertices", offset=offset, limit=1024)
        items.extend(page["items"])
        if not page["hasMore"]:
            break
        offset = page["nextOffset"]
    assert len(items) == 4225
    assert [item["key"] for item in items] == list(range(1, 4226))
    assert items[-1] == {"key": 4225, "value": 8450}
    for args in ({"tile_x": 1, "tile_y": 0}, {"tile_y": 0}):
        with pytest.raises(lupa_mod.LuaError):
            call("get_terrain_tile", **args)


def test_data_layers_and_water_cover_negative_tiles(runtime):
    _, call = runtime
    assert call("get_map_data")["layers"] == [{"name": "forest_mask", "width": 3, "height": 2}]
    assert call("get_map_data", layer="forest_mask", offset=2, limit=4)["values"] == [2, 10, 11, 12]
    with pytest.raises(lupa_mod.LuaError):
        call("get_map_data", layer="missing")
    assert call("list_map_entities", kind="WATER_MESH")["total"] == 1


def test_nested_opaque_stock_records_use_generated_types(runtime):
    lua, call = runtime
    stocks = lua.table_from([OpaqueGameValue(capacity=42, mixedTypes=False)])
    rules = lua.table_from([OpaqueGameValue(input=lua.table_from([lua.table_from([1, 2])]), capacity=3)])
    lua.globals().components[100][83] = OpaqueGameValue(stocks=stocks, rules=rules, thrownAwayCargo=0)
    stock = call("get_entity", id=100, components=["STOCK_LIST"])["components"]["STOCK_LIST"]
    assert stock["stocks"][0]["capacity"] == 42
    assert stock["stocks"][0]["mixedTypes"] is False
    assert stock["rules"][0]["input"] == [[1, 2]]
    page = call("get_component_collection", id=100, component="STOCK_LIST", field="stocks")
    assert page["items"][0]["value"]["capacity"] == 42
    # Full index fallback must work even when the specialized iterator refuses.
    lua.execute("api.engine.forEachEntityWithComponent=function() error('unsupported') end")
    assert call("list_map_entities", kind="STOCK_LIST")["total"] == 1
    assert call("list_map_entities", kind="SIM_CARGO")["total"] == 0


def test_snapshot_keeps_ids_after_insert_delete_and_releases(runtime):
    lua, call = runtime
    lua.execute("components[102]={[2]={}}")
    first = call("list_map_entities", kind="TOWN", limit=1, snapshot="new")
    token = first["snapshot"]
    assert first["total"] == 3 and first["items"][0]["id"] == 100
    lua.execute("components[99]={[2]={}}; components[101]=nil; components[103]={[2]={}}")
    second = call("list_map_entities", kind="TOWN", offset=1, limit=2, snapshot=token)
    assert second["total"] == 3
    assert second["items"][0] == {"id": 101, "missing": True}
    assert second["items"][1]["id"] == 102
    assert not second["hasMore"]
    with pytest.raises(lupa_mod.LuaError, match="kind does not match"):
        call("list_map_entities", kind="LINE", snapshot=token)
    assert call("release_map_snapshot", snapshot=token)["released"] is True
    assert call("release_map_snapshot", snapshot=token)["released"] is False
    with pytest.raises(lupa_mod.LuaError, match="expired or unknown"):
        call("list_map_entities", kind="TOWN", snapshot=token)


def test_snapshot_eviction_expiry_and_start_validation(runtime):
    lua, call = runtime
    lua.execute("os.clock=function() return 10 end")
    tokens = [call("list_map_entities", kind="TOWN", snapshot="new")["snapshot"] for _ in range(5)]
    with pytest.raises(lupa_mod.LuaError, match="expired or unknown"):
        call("list_map_entities", kind="TOWN", snapshot=tokens[0])
    assert call("list_map_entities", kind="TOWN", snapshot=tokens[-1])["total"] == 2
    with pytest.raises(lupa_mod.LuaError, match="offset 0"):
        call("list_map_entities", kind="TOWN", snapshot="new", offset=1)
    lua.execute("os.clock=function() return 311 end")
    with pytest.raises(lupa_mod.LuaError, match="expired or unknown"):
        call("list_map_entities", kind="TOWN", snapshot=tokens[-1])


@pytest.mark.parametrize("first", [0, 1])
def test_matrix_columns_preserve_all_four_with_native_indexing(first):
    lua = lupa_mod.LuaRuntime()
    lua.execute(MOCK_API)
    columns = {i+first: OpaqueGameValue(x=i+1, y=0, z=0, w=1 if i==3 else 0) for i in range(4)}
    matrix = OpaqueGameValue(cols=lambda self, index: columns[index])
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    value = script["_internal"]["toPlain"](matrix)
    result = json.loads(script["_internal"]["json"]["encode"](value))
    assert [column["x"] for column in result["columns"]] == [1, 2, 3, 4]
