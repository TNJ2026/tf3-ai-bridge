-- Read-only. Resolve town by name in the CURRENT map, never by historical entity ids.
local CT=api.type.ComponentType
local map=B.commands.get_map_info()
local town
for _,t in ipairs(map.towns) do if t.name=="镇江" then assert(not town,"duplicate town name");town=t end end
assert(town,"Zhenjiang is absent from the current map")
local out={state=B.commands.get_game_state(),town=town,cargos={},demand={},buildings={},industries={},neighbors={},facilities=B.commands.list_facilities({}),lines=B.commands.list_lines({}),vehicles=B.commands.list_vehicles({})}
out.townData=B.commands.get_entity({id=town.id,components={"TOWN"}})
local function distance(p) return math.sqrt((p.x-town.position.x)^2+(p.y-town.position.y)^2) end
for id,name in pairs(api.res.cargoTypeRep.getAll(true)) do local c=api.res.cargoTypeRep.get(id);out.cargos[#out.cargos+1]={id=id,resource=name,name=c.name,timeToDeliverInSeconds=c.timeToDeliverInSeconds} end
local totals={}
api.engine.forEachEntityWithComponent(function(id)
 local b=api.engine.getComponent(id,CT.TOWN_BUILDING)
 if b.town==town.id then
  local row={id=id,data=B.toPlain(b,0,nil,"Engine.Component.TownBuilding"),demand={}}
  local con=api.engine.getComponent(b.construction,CT.CONSTRUCTION)
  if con then local p=con.transf:getTransl();row.position={x=p.x,y=p.y,z=p.z} end
  if b.stockList and b.stockList>=0 and api.engine.entityExists(b.stockList) then
   for _,cargo in ipairs(out.cargos) do
    local amount=api.engine.util.stock.getCargoMaxConsumptionPerYear(b.stockList,cargo.id)
    if amount>0 then
     local consumed=api.engine.util.stock.getCargoConsumedPerYear(b.stockList,cargo.id)
     row.demand[#row.demand+1]={cargo=cargo.id,maximum=amount,consumed=consumed}
     local t=totals[cargo.id] or {cargo=cargo.id,name=cargo.name,maximum=0,consumed=0,buildings=0};totals[cargo.id]=t
     t.maximum=t.maximum+amount;t.consumed=t.consumed+consumed;t.buildings=t.buildings+1
    end
   end
  end
  out.buildings[#out.buildings+1]=row
 end
end,CT.TOWN_BUILDING)
for _,t in pairs(totals) do out.demand[#out.demand+1]=t end
for _,i in ipairs(map.industries) do
 local c=api.engine.getComponent(i.id,CT.INDUSTRY)
 local r={id=i.id,resource=i.fileName,position=i.position,straightDistance=distance(i.position),level=c.level,production={},consumption={}}
 local io=api.engine.util.stock.getInputsOutputsFromRules(c.stockList)
 r.inputs=B.toPlain(io[1]);r.outputs=B.toPlain(io[2])
 for _,cargo in ipairs(io[2]) do r.production[#r.production+1]={cargo=cargo,maximum=api.engine.util.stock.getCargoMaxProductionPerYear(c.stockList,cargo),actual=api.engine.util.stock.getCargoProducedPerYear(c.stockList,cargo)} end
 for _,cargo in ipairs(io[1]) do r.consumption[#r.consumption+1]={cargo=cargo,maximum=api.engine.util.stock.getCargoMaxConsumptionPerYear(c.stockList,cargo)} end
 out.industries[#out.industries+1]=r
end
table.sort(out.industries,function(a,b)return a.straightDistance<b.straightDistance end)
for _,t in ipairs(map.towns) do if t.id~=town.id then out.neighbors[#out.neighbors+1]={id=t.id,name=t.name,position=t.position,straightDistance=distance(t.position)} end end
table.sort(out.neighbors,function(a,b)return a.straightDistance<b.straightDistance end)
return B.json.encode(out)
