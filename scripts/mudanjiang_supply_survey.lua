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
return B.json.encode(out)
