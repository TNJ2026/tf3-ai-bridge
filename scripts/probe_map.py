"""Read-only live map capability probe; writes results into the project."""
import asyncio
import json
from pathlib import Path

from tf3_mcp.bridge import Bridge

LUA = r'''
local out = { components = {} }
local function probe(name, fn)
  local ok, result = pcall(fn)
  out[name] = {ok = ok, result = ok and toPlain(result) or nil, error = not ok and tostring(result) or nil}
end
probe("bounds", function() return api.engine.terrain.getBoundingBox() end)
probe("baseResolution", function() return api.engine.terrain.getBaseResolution() end)
probe("highResolution", function() return api.engine.terrain.getHighResolution() end)
probe("gameTime", function() return api.engine.getComponent(api.engine.util.getWorld(), api.type.ComponentType.GAME_TIME) end)
for _, name in ipairs({"TOWN", "INDUSTRY", "CONSTRUCTION", "TOWN_BUILDING", "BASE_NODE", "BASE_EDGE", "STATION", "STATION_GROUP", "VEHICLE_DEPOT", "TRANSPORT_VEHICLE", "TERRAIN", "TERRAIN_TILE", "TERRAIN_TILE_HEIGHTMAP", "WATER_MESH", "SIM_PERSON", "SIM_CARGO", "STOCK_LIST", "MODEL_INSTANCE_LIST", "TRANSPORT_NETWORK"}) do
  local count, ids = 0, {}
  local ok, err = pcall(function()
    local ct = api.type.ComponentType[name]
    if ct == nil then error("component unavailable") end
    api.engine.forEachEntityWithComponent(function(id)
      count = count + 1
      if #ids < 2 then ids[#ids + 1] = id end
    end, ct)
  end)
  out.components[name] = {ok = ok, count = count, sampleIds = ids, error = not ok and tostring(err) or nil}
end
probe("lines", function() return api.engine.system.lineSystem.getLines() end)
probe("personCount", function() return api.engine.system.simPersonSystem.getCount() end)
return out
'''

DETAIL_LUA = r'''
local out = {}
local function probe(name, fn)
  local ok, result = pcall(fn)
  out[name] = {ok = ok, result = ok and toPlain(result) or nil, error = not ok and tostring(result) or nil}
end
local CT = api.type.ComponentType
probe("bounds", function()
  local b = api.engine.terrain.getBoundingBox()
  return {min = {x=b.min.x,y=b.min.y}, max = {x=b.max.x,y=b.max.y}}
end)
probe("network", function()
  local map = api.engine.system.streetSystem.getNode2SegmentMap()
  local nodes, edges, sample = 0, {}, nil
  for node, segments in pairs(map) do
    nodes = nodes + 1
    for _, id in pairs(segments) do edges[id] = true; sample = id end
  end
  local count = 0
  for _ in pairs(edges) do count = count + 1 end
  local e = sample and api.engine.getComponent(sample, CT.BASE_EDGE)
  return {nodes=nodes, edges=count, sample=e and {id=sample,node0=e.node0,node1=e.node1,position0=toPlain(e.position0),position1=toPlain(e.position1),roadTemplate=e.roadTemplate}}
end)
probe("mapMetadata", function()
  local m = api.engine.terrain.makeMapFromGame(false, true, true, false)
  local towns, industries = {}, {}
  for _, t in pairs(m.towns) do towns[#towns+1] = {id=t.existing,name=t.name,position={x=t.pos.x,y=t.pos.y}} end
  for _, i in pairs(m.industries) do industries[#industries+1] = {id=i.existing,fileName=i.fileName,position={x=i.pos.x,y=i.pos.y}} end
  return {climateId=m.climateId,towns=towns,industries=industries}
end)
probe("industryFields", function()
  local sample
  api.engine.forEachEntityWithComponent(function(id) if not sample then sample=id end end, CT.INDUSTRY)
  local i = api.engine.getComponent(sample, CT.INDUSTRY)
  return {id=sample,stockList=i.stockList,construction=i.construction,level=i.level,maxLevel=i.maxLevel,upgradeProgress=i.upgradeProgress}
end)
probe("heightSamples", function()
  local b = api.engine.terrain.getBoundingBox()
  local samples = {}
  for i=0,2 do for j=0,2 do
    local x=b.min.x+(b.max.x-b.min.x)*(i+0.5)/3
    local y=b.min.y+(b.max.y-b.min.y)*(j+0.5)/3
    local p=api.type.Vec2f.new(x,y)
    samples[#samples+1]={x=x,y=y,height=api.engine.terrain.getHeightAt(p),water=api.engine.terrain.isOnWater(p)}
  end end
  return samples
end)
return out
'''

async def main():
    bridge = Bridge()
    result = {"heartbeat": bridge.heartbeat()}
    result["ping"] = await bridge.call("ping", {"echo": "read-only map inspection"})
    result["census"] = await bridge.call("eval", {"code": LUA}, timeout=30)
    result["details"] = await bridge.call("eval", {"code": DETAIL_LUA}, timeout=30)
    result["samples"] = {}
    for name in ["TOWN", "INDUSTRY", "BASE_NODE", "BASE_EDGE", "TERRAIN", "TOWN_BUILDING", "STOCK_LIST", "WATER_MESH"]:
        ids = result["census"]["components"][name]["sampleIds"]
        if ids:
            result["samples"][name] = await bridge.call("get_entity", {"id": ids[0], "components": [name, "NAME"]})
    path = Path(__file__).resolve().parents[1] / "map_probe.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved probe to {path}")
    for name, detail in result["details"].items():
        print(name, "OK" if detail["ok"] else detail.get("error"))
    metadata = result["details"]["mapMetadata"].get("result", {})
    for name in ("towns", "industries"):
        items = metadata.get(name, [])
        print(name, len(items), "sample:", items[:1])

if __name__ == "__main__":
    asyncio.run(main())
