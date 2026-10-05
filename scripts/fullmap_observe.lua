local CT=api.type.ComponentType;local cargos={1,6,7,9,12,13,18,20,23,33};local out={vehicles={},loaded=0,noPath={},cities={},problemLines={}}
for _,id in ipairs(api.engine.getEntitiesWithComponent(CT.TRANSPORT_VEHICLE,{requireOwnedByPlayer=api.engine.util.getPlayer()}))do
 local v=api.engine.getComponent(id,CT.TRANSPORT_VEHICLE);local row={id=id,line=v.line,state=v.state,noPath=v.noPath,stopIndex=v.stopIndex,load={}};local total=0
 for _,c in ipairs(cargos)do local n=api.engine.system.simEntityAtVehicleSystem.getVehicleSimEntitiesCountForCargoType(id,c);if n>0 then row.load[tostring(c)]=n;total=total+n end end
 row.total=total;out.loaded=out.loaded+total;out.vehicles[#out.vehicles+1]=row;if v.noPath then out.noPath[#out.noPath+1]=id end
end
for _,p in ipairs(api.engine.system.lineSystem.getProblemLines(api.engine.util.getPlayer()))do out.problemLines[#out.problemLines+1]={line=p[1],problem=B.toPlain(p[2])}end
if FULL then
 out.townSupply={}
 for _,id in ipairs(api.engine.getEntitiesWithComponent(CT.TOWN))do
  local r={town=id,supply=0,demand=0,cargos={}}
  for _,u in ipairs({api.type.enum.LandUseType.RESIDENTIAL,api.type.enum.LandUseType.COMMERCIAL,api.type.enum.LandUseType.INDUSTRIAL})do
   for c,v in pairs(api.engine.system.townBuildingSystem.getCargoSupplyAndLimit(id,u))do if c>0 then r.supply=r.supply+v[1];r.demand=r.demand+v[2];local k=tostring(c);r.cargos[k]=r.cargos[k]or{supply=0,demand=0};r.cargos[k].supply=r.cargos[k].supply+v[1];r.cargos[k].demand=r.cargos[k].demand+v[2]end end
  end
  out.townSupply[#out.townSupply+1]=r
 end
 api.engine.forEachEntityWithComponent(function(id)local b=api.engine.getComponent(id,CT.TOWN_BUILDING);if b.stockList>=0 and api.engine.entityExists(b.stockList)then
  local key=tostring(b.town);out.cities[key]=out.cities[key]or{deliveredPerYear=0,cargos={}};local r=out.cities[key]
  for _,c in ipairs(cargos)do local n=api.engine.util.stock.getCargoTypeDeliveredPerYear(b.stockList,c);if n>0 then r.deliveredPerYear=r.deliveredPerYear+n;r.cargos[tostring(c)]=(r.cargos[tostring(c)]or 0)+n end end
 end end,CT.TOWN_BUILDING)
end
return B.json.encode(out)
