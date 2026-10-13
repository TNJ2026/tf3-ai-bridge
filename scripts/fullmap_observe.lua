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
  local panel=B.commands.get_town_cargo_supply({town=id})
  for _,v in ipairs(panel.items) do
   r.supply=r.supply+v.supply;r.demand=r.demand+v.demand
   r.cargos[tostring(v.cargo)]=v
  end
  r.scope=panel.scope;r.gameTime=panel.gameTime
  out.townSupply[#out.townSupply+1]=r
  out.cities[tostring(id)]={cargos=r.cargos,scope=panel.scope,annualDeliveredKnown=false}
 end
end
return B.json.encode(out)
