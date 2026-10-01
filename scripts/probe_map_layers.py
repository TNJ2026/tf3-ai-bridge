"""Read-only diagnostic for the game's less commonly exposed map layers."""
import asyncio
import json
from pathlib import Path
from tf3_mcp.bridge import Bridge

CODE = r'''
local out = {}
local function probe(name, fn)
  local ok, result = pcall(fn)
  out[name] = {ok=ok, result=ok and result or nil, error=not ok and tostring(result):match("^[^\n]+") or nil}
end
for _, kind in ipairs({"TERRAIN", "TERRAIN_TILE", "TERRAIN_TILE_HEIGHTMAP", "TERRAIN_TILE_BRUSH", "WATER_MESH", "MODEL_INSTANCE_LIST", "ASSET_GROUP", "SIM_CARGO", "STOCK_LIST"}) do
  probe(kind, function()
    local ids = api.engine.getEntitiesWithComponent(api.type.ComponentType[kind])
    local n, sample = 0, nil
    for _, id in pairs(ids) do n=n+1; if not sample then sample=id end end
    return {count=n, sample=sample}
  end)
end
probe("waterIndex", function()
  local b=api.engine.terrain.getBoundingBox()
  local ids=api.engine.system.riverSystem.getWaterMeshEntities(
    api.type.Vec2i.new(math.floor(b.min.x/256),math.floor(b.min.y/256)),
    api.type.Vec2i.new(math.ceil(b.max.x/256)-1,math.ceil(b.max.y/256)-1))
  local n,sample=0,nil
  for _,id in pairs(ids) do n=n+1; if not sample then sample=id end end
  local wm=sample and api.engine.getComponent(sample,api.type.ComponentType.WATER_MESH)
  return {count=n,sample=sample,componentReadable=wm~=nil}
end)
probe("terrainWorld", function()
  local t=api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.TERRAIN)
  return {size={x=t.size.x,y=t.size.y},waterLevel=t.waterLevel,dataMaps=toPlain(t.dataMaps)}
end)
probe("modelSpatialIndex", function()
  local b=api.engine.terrain.getBoundingBox()
  local ids=api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(0,0),math.sqrt(b.max.x*b.max.x+b.max.y*b.max.y)+1,api.type.ComponentType.MODEL_INSTANCE_LIST)
  local n, sample = 0,nil
  for _,id in pairs(ids) do n=n+1; if not sample then sample=id end end
  local c=sample and api.engine.getComponent(sample,api.type.ComponentType.MODEL_INSTANCE_LIST)
  return {count=n,sample=sample,fat=c and #c.fatInstances,thin=c and #c.thinInstances}
end)
probe("tileData", function()
  local id=api.engine.terrain.getHeightmapEntity(api.type.Vec2i.new(0,0))
  local result={id=id}
  for _, kind in ipairs({"TERRAIN_TILE", "TERRAIN_TILE_HEIGHTMAP", "TERRAIN_TILE_BRUSH"}) do
    local ok,c=pcall(api.engine.getComponent,id,api.type.ComponentType[kind])
    result[kind]={readable=ok and c~=nil}
    if ok and c then
      if kind=="TERRAIN_TILE" then result[kind].position={x=c.position.x,y=c.position.y} end
      if kind=="TERRAIN_TILE_HEIGHTMAP" then result[kind].count=#c.vertices end
      if kind=="TERRAIN_TILE_BRUSH" then result[kind].count=#c.materialIndexBrush end
    end
  end
  return result
end)
probe("dataMapSample", function()
  local terrain=api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.TERRAIN)
  local result={}
  for name,m in pairs(terrain.dataMaps) do
    local size=m:getSize()
    result[name]={width=size.x,height=size.y,value=m:at(0,0)}
  end
  return result
end)
probe("cornerTile", function()
  local b=api.engine.terrain.getBoundingBox()
  local id=api.engine.terrain.getHeightmapEntity(api.type.Vec2i.new(math.floor(b.min.x/256),math.floor(b.min.y/256)))
  local tile=api.engine.getComponent(id,api.type.ComponentType.TERRAIN_TILE)
  return {id=id,position={x=tile.position.x,y=tile.position.y}}
end)
probe("entityScan", function()
  local kinds={"STOCK_LIST","SIM_CARGO","TERRAIN_TILE_BRUSH","ASSET_GROUP"}
  local result={entities=0,counts={},samples={}}
  for _,kind in ipairs(kinds) do result.counts[kind]=0 end
  api.engine.forEachEntity(function(id)
    result.entities=result.entities+1
    for _,kind in ipairs(kinds) do
      local comp=api.engine.getComponent(id,api.type.ComponentType[kind])
      if comp~=nil then
        result.counts[kind]=result.counts[kind]+1
        if not result.samples[kind] then result.samples[kind]=id end
      end
    end
  end)
  return result
end)
return json.encode(out)
'''

async def main():
    result = json.loads(await Bridge().call("eval", {"code": CODE}, timeout=30))
    path = Path(__file__).resolve().parents[1] / "map_layer_capabilities.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
