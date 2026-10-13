-- Read-only survey. Resolve every entity from the current map.
local CT=api.type.ComponentType
local map=B.commands.get_map_info({})
local out={state=B.commands.get_game_state({}),towns={},industries={},cargos={}}
for id,resource in pairs(api.res.cargoTypeRep.getAll(true)) do
 local c=api.res.cargoTypeRep.get(id)
 out.cargos[#out.cargos+1]={id=id,resource=resource,name=c.name}
end
for _,t in ipairs(map.towns) do
 local comp=api.engine.getComponent(t.id,CT.TOWN)
 local r={id=t.id,name=t.name,position=t.position,needs=B.toPlain(comp.cargoNeeds),demand={}}
 out.towns[#out.towns+1]=r
end
for _,t in ipairs(out.towns) do
 local panel=B.commands.get_town_cargo_supply({town=t.id})
 t.supply=panel;t.demandScope="native city panel"
 for _,row in ipairs(panel.items) do t.demand[tostring(row.cargo)]=row.demand end
end
for _,i in ipairs(map.industries) do
 local c=api.engine.getComponent(i.id,CT.INDUSTRY)
 local io=api.engine.util.stock.getInputsOutputsFromRules(c.stockList)
 local r={id=i.id,resource=i.fileName,position=i.position,inputs=B.toPlain(io[1]),outputs=B.toPlain(io[2]),production={}}
 for _,cargo in ipairs(io[2]) do
  r.production[#r.production+1]={cargo=cargo,capacity=api.engine.util.stock.getCargoMaxProductionPerYear(c.stockList,cargo),actual=api.engine.util.stock.getCargoProducedPerYear(c.stockList,cargo)}
 end
 out.industries[#out.industries+1]=r
end
return B.json.encode(out)
