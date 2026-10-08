"""Run the saved read-only map handlers against a live game without reloading its save.

The script is loaded into a separate Lua environment. Its callbacks are not registered;
this verifies new code but does not upgrade the running GUI bridge.
"""
import asyncio
import json
from pathlib import Path

from tf3_mcp.bridge import Bridge

ROOT = Path(__file__).resolve().parents[1]


async def main():
    source = (ROOT / "mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua").read_text(encoding="utf-8")
    code = (
        'local env = setmetatable({}, {__index=_G})\n'
        'local script = assert(load(' + json.dumps(source, ensure_ascii=False)
        + ', "=map_fix_validation", "t", env))()\n'
        'local c = script._internal.commands\n'
        'local result = {map=c.get_map_info(), pages={}}\n'
        'for _, kind in ipairs({"TOWN", "INDUSTRY", "CONSTRUCTION", "TOWN_BUILDING", "BASE_NODE", "BASE_EDGE", "STATION", "STATION_GROUP", "VEHICLE_DEPOT", "TRANSPORT_VEHICLE", "SIM_PERSON", "LINE", "WATER_MESH", "MODEL_INSTANCE_LIST", "ASSET_GROUP", "SIM_CARGO", "STOCK_LIST", "TERRAIN_TILE_BRUSH"}) do\n'
        ' result.pages[kind] = c.list_map_entities({kind=kind,limit=2})\n'
        'end\n'
        'local id = result.pages.INDUSTRY.items[1].id\n'
        'result.industry = c.get_entity({id=id,components={"INDUSTRY", "STOCK_LIST"}})\n'
        'result.grid=c.get_terrain_grid({columns=3,rows=3,limit=4})\n'
        'result.gridNext=c.get_terrain_grid({columns=3,rows=3,limit=4,offset=result.grid.nextOffset})\n'
        'result.baseGrid=c.get_terrain_grid({columns=3,rows=3,limit=4,mode="base"})\n'
        'result.tile=c.get_terrain_tile({tile_x=math.floor(result.map.bounds.min.x/256),tile_y=math.floor(result.map.bounds.min.y/256)})\n'
        'result.rawHeights=c.get_component_collection({id=result.tile.id,component="TERRAIN_TILE_HEIGHTMAP",field="vertices",limit=3})\n'
        'result.rawHeightsEnd=c.get_component_collection({id=result.tile.id,component="TERRAIN_TILE_HEIGHTMAP",field="vertices",offset=result.rawHeights.total-3,limit=3})\n'
        'local offset,count=0,0\n'
        'repeat\n'
        ' local page=c.get_component_collection({id=result.tile.id,component="TERRAIN_TILE_HEIGHTMAP",field="vertices",offset=offset,limit=1024})\n'
        ' for _,item in ipairs(page.items) do count=count+1; assert(item.key==count) end\n'
        ' offset=page.nextOffset\n'
        'until not offset\n'
        'result.rawHeightAudit={count=count,complete=count==result.rawHeights.total}\n'
        'result.layers=c.get_map_data({})\n'
        'result.layerSamples={}\n'
        'for _,l in ipairs(result.layers.layers) do result.layerSamples[l.name]=c.get_map_data({layer=l.name,limit=3}) end\n'
        'local model=result.pages.MODEL_INSTANCE_LIST.items[1]\n'
        'result.models=c.get_component_collection({id=model.id,component="MODEL_INSTANCE_LIST",field=model.thinCount>0 and "thinInstances" or "fatInstances",limit=2})\n'
        'local asset=result.pages.ASSET_GROUP.items[1]\n'
        'result.assets=c.get_component_collection({id=asset.id,component="MODEL_INSTANCE_LIST",field=asset.thinCount>0 and "thinInstances" or "fatInstances",limit=2})\n'
        'local water=result.pages.WATER_MESH.items[1]\n'
        'result.waterVertices=c.get_component_collection({id=water.id,component="WATER_MESH",field="vertices",limit=3})\n'
        'return script._internal.json.encode(result)'
    )
    result = json.loads(await Bridge().call("eval", {"code": code}, timeout=30))
    # JSON text avoids a second depth-limited serialization pass in eval.
    assert result["map"]["width"] > 0
    assert isinstance(result["map"]["towns"][0]["position"]["x"], (float, int))
    assert isinstance(result["industry"]["components"]["INDUSTRY"]["level"], (float, int))
    assert isinstance(result["pages"]["BASE_EDGE"]["items"][0]["components"]["BASE_EDGE"]["node0"], int)
    assert result["grid"]["total"] == 9 and result["gridNext"]["offset"] == 4
    assert len(result["grid"]["heights"]) == len(result["grid"]["water"]) == 4
    assert result["rawHeights"]["total"] > 2000
    assert result["rawHeightsEnd"]["hasMore"] is False
    assert result["rawHeightsEnd"]["items"][-1]["key"] == result["rawHeights"]["total"]
    assert isinstance(result["waterVertices"]["items"][0]["value"]["x"], (float, int))
    assert result["models"]["items"][0]["value"]["modelName"]
    assert result["rawHeightAudit"]["complete"]
    assert result["assets"]["items"][0]["value"]["modelName"]
    output = ROOT / "map_fix_validation.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for kind, page in result["pages"].items():
        print(kind, "total:", page["total"], "nextOffset:", page.get("nextOffset"))
    def markers(value, path=""):
        if isinstance(value, dict):
            if "_unavailable" in value or "_truncated" in value:
                print("UNREADABLE", path)
            for key, child in value.items():
                markers(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                markers(child, f"{path}[{index}]")
    markers(result)
    print("Live field assertions passed. Saved:", output)


if __name__ == "__main__":
    asyncio.run(main())
