local CT=api.type.ComponentType
local out={state=B.commands.get_game_state({}),lines={},vehicles={},problems={}}
for _,id in ipairs(api.engine.system.lineSystem.getLines())do
 local n=api.engine.getComponent(id,CT.NAME)
 if n and n.name:find('全图供给·',1,true)==1 then
  local l=api.engine.getComponent(id,CT.LINE);local row={id=id,name=n.name,stops={},vehicles={}}
  for _,s in ipairs(l.stops)do row.stops[#row.stops+1]={group=s.stationGroup,station=s.station,terminal=s.terminal}end
  for _,vid in ipairs(api.engine.system.transportVehicleSystem.getLineVehicles(id))do
   local v=api.engine.getComponent(vid,CT.TRANSPORT_VEHICLE)
   local r={id=vid,line=v.line,state=v.state,noPath=v.noPath,userStopped=v.userStopped,depot=v.depot,stopIndex=v.stopIndex,maintenanceStation=v.maintenanceStation,parts={},visitedStops={}}
   for _,part in ipairs(v.transportVehicleConfig.vehicles)do
    local configs={};for _,lc in ipairs(part.part.compartment2loadConfig)do configs[#configs+1]=lc.loadConfigIndex end
    r.parts[#r.parts+1]={model=api.res.modelRep.getName(part.part.modelId),maintenanceState=part.maintenanceState,maintenanceChange=part.maintenanceChange,loadConfigIndices=configs}
   end
   for _,s in ipairs(v.visitedStops)do r.visitedStops[#r.visitedStops+1]=s end
   row.vehicles[#row.vehicles+1]=vid;out.vehicles[#out.vehicles+1]=r
  end
  out.lines[#out.lines+1]=row
 end
end
for _,p in ipairs(api.engine.system.lineSystem.getProblemLines(api.engine.util.getPlayer()))do out.problems[#out.problems+1]=B.toPlain(p)end
return B.json.encode(out)
