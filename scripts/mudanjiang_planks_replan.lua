local CT=api.type.ComponentType;local town=api.engine.getComponent(48457,CT.TOWN)
local out={state=B.commands.get_game_state({}),map=B.commands.get_map_info({}),needs=B.toPlain(town.cargoNeeds),cargoTypes={},industries={},demand={},buildings=0}
for id,name in pairs(api.res.cargoTypeRep.getAll()) do out.cargoTypes[tostring(id)]=name end
local wanted={};for _,district in ipairs(town.cargoNeeds) do for _,pair in ipairs(district) do wanted[pair[1]]=true end end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(868,-244),2000,CT.TOWN_BUILDING)) do local c=api.engine.getComponent(id,CT.TOWN_BUILDING)
 if c.town==48457 and c.stockList>=0 and api.engine.entityExists(c.stockList) then out.buildings=out.buildings+1;local sl=c.stockList
  for cargo in pairs(wanted) do
   local key=tostring(cargo);out.demand[key]=out.demand[key] or {capacity=0,consumed=0,delivered=0}
   local row=out.demand[key];row.capacity=row.capacity+api.engine.util.stock.getCargoMaxConsumptionPerYear(sl,cargo)
   row.consumed=row.consumed+api.engine.util.stock.getCargoConsumedPerYear(sl,cargo)
   row.delivered=row.delivered+api.engine.util.stock.getCargoTypeDeliveredPerYear(sl,cargo)
  end
 end
end
for _,v in ipairs(out.map.industries) do
 local c=api.engine.getComponent(v.id,CT.INDUSTRY);local io=api.engine.util.stock.getInputsOutputsFromRules(c.stockList)
 local row={id=v.id,construction=c.construction,position=v.position,fileName=v.fileName,inputs=B.toPlain(io[1]),outputs=B.toPlain(io[2]),production={}}
 for _,cargo in ipairs(io[2]) do row.production[#row.production+1]={cargo=cargo,capacity=api.engine.util.stock.getCargoMaxProductionPerYear(c.stockList,cargo),actual=api.engine.util.stock.getCargoProducedPerYear(c.stockList,cargo)} end
 out.industries[#out.industries+1]=row
end
out.access={}
for _,id in ipairs({59863,48615}) do local p=api.engine.getComponent(id,CT.BASE_NODE).position;out.access[#out.access+1]={node=id,x=p.x,y=p.y,z=p.z,degree=#api.engine.system.streetSystem.getNodeSegments(id)} end
out.spur={}
for i=0,15 do local x,y=555.90002441406,-1529.5+i*285.5/15;local p=api.type.Vec2f.new(x,y);out.spur[#out.spur+1]={x=x,y=y,h=api.engine.terrain.getHeightAt(p),water=api.engine.terrain.isOnWater(p)} end
out.nearSpur={}
for _,kind in ipairs({'CONSTRUCTION','TOWN_BUILDING','BASE_EDGE'}) do
 out.nearSpur[kind]={}
 for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(555.9,-1386.75),170,CT[kind])) do
 local b=api.engine.getComponent(id,CT.BOUNDING_VOLUME);local row={id=id,min=B.toPlain(b.bbox.min),max=B.toPlain(b.bbox.max)}
 if kind=='BASE_EDGE' then local e=api.engine.getComponent(id,CT.BASE_EDGE);row.node0=e.node0;row.node1=e.node1;row.p0=B.toPlain(e.position0);row.p1=B.toPlain(e.position1) end
 out.nearSpur[kind][#out.nearSpur[kind]+1]=row
 end
end
return B.json.encode(out)
