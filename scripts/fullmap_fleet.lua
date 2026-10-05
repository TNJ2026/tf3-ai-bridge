local task=B.json.decode(TASKJSON);local action=ACTION;local CT=api.type.ComponentType
local lineId
for _,id in ipairs(api.engine.system.lineSystem.getLines())do
 local n=api.engine.getComponent(id,CT.NAME)
 if n and n.name==task.name then assert(not lineId,'duplicate line');lineId=id end
end
assert(lineId,'line missing');local line=api.engine.getComponent(lineId,CT.LINE)
local mode=api.type.enum.TransportMode[task.mode]
local function vehicles()
 local out={}
 for _,id in ipairs(api.engine.system.transportVehicleSystem.getLineVehicles(lineId))do
  local v=api.engine.getComponent(id,CT.TRANSPORT_VEHICLE)
  local models={};for _,part in ipairs(v.transportVehicleConfig.vehicles)do models[#models+1]=api.res.modelRep.getName(part.part.modelId)end
  out[#out+1]={id=id,line=v.line,noPath=v.noPath,depot=v.depot,state=v.state,userStopped=v.userStopped,stopIndex=v.stopIndex,models=models,maintenanceStation=v.maintenanceStation}
 end
 table.sort(out,function(a,b)return a.id<b.id end);return out
end
local out={line=lineId,vehicles=vehicles(),mode=task.mode}
if action=='verify'then return B.json.encode(out)end
assert(#out.vehicles==#task.expectedVehicles,'unrecorded vehicle count')
for i,id in ipairs(task.expectedVehicles)do assert(out.vehicles[i].id==id,'unrecorded vehicle identity')end
local model=api.res.modelRep.find(task.model);assert(model>=0,'model missing')
local md=api.res.modelRep.get(model).metadata;local tv=md.transportVehicle
local compatible=false;for _,m in ipairs(tv.transportModes)do compatible=compatible or m==mode end
assert(compatible,'model transport mode incompatible')
local year=api.engine.util.getCalendarDate(api.engine.getComponent(api.engine.util.getWorld(),CT.GAME_TIME).gameTime).year
assert(md.availability.yearFrom<=year and (md.availability.yearTo==0 or md.availability.yearTo>=year),'model unavailable')
for _,cargo in ipairs(task.cargos)do
 local can=false
 for _,comp in ipairs(tv.compartments)do for _,lc in ipairs(comp.loadConfigs)do can=can or api.res.cargoTypeRep.hasCargoType(lc.cargoEntry.cargoTypeSet,cargo,false)end end
 assert(can,'model cannot carry required cargo '..cargo)
end
local firstStop=line.stops[1];local g=api.engine.getComponent(firstStop.stationGroup,CT.STATION_GROUP)
local first=api.engine.getComponent(g.stations[firstStop.station+1],CT.STATION).terminals[firstStop.terminal+1].vehicleNodeId
local candidates={}
api.engine.forEachEntityWithComponent(function(id)
 local c=api.engine.getComponent(id,CT.CONSTRUCTION);local pos=c.transf:cols(3)
 for _,wanted in ipairs(task.depots)do
  if math.abs(pos.x-wanted.position.x)<.2 and math.abs(pos.y-wanted.position.y)<.2 then
   for _,dep in ipairs(c.depots)do
    local d=api.engine.getComponent(dep,CT.VEHICLE_DEPOT)
    if d and d.transportModes[mode]and #d.outNodes>0 and #d.inNodes>0 then
     local parked=#api.engine.system.transportVehicleSystem.getDepotVehicles(dep)
     if task.mode~='HELICOPTER'or parked<5 then
      local a=api.engine.util.pathfinding.findPathNodeToNode(d.outNodes,{first},{mode})
      local b=api.engine.util.pathfinding.findPathNodeToNode({first},d.inNodes,{mode})
      if #a>0 and #b>0 then
       local distance=0
       for _,step in ipairs(a)do distance=distance+api.engine.getComponent(step[1].entity,CT.TRANSPORT_NETWORK).edges[step[1].index+1].geometry.length end
       if task.mode~='TRUCK'then distance=math.sqrt((pos.x-task.origin.x)^2+(pos.y-task.origin.y)^2)end
       candidates[#candidates+1]={depot=dep,facility=wanted.id,distance=distance,parked=parked}
      end
     end
    end
   end
  end
 end
end,CT.CONSTRUCTION)
assert(#candidates>0,'no compatible reachable depot with parking')
table.sort(candidates,function(a,b)return a.distance<b.distance end);out.selected=candidates[1];out.model=task.model
if action~='build'then return B.json.encode(out)end
local before={};for _,v in ipairs(out.vehicles)do before[v.id]=true end
B.commands.buy_vehicles({depot=out.selected.depot,model=task.model,count=1,line=lineId},function(ok,r)out.accepted=ok;out.result=r end)
out.vehicles=vehicles();out.newVehicles={}
for _,v in ipairs(out.vehicles)do if not before[v.id]then out.newVehicles[#out.newVehicles+1]=v end end
out.verified=out.accepted==true and out.result and #out.result.failures==0 and #out.newVehicles==1 and #out.vehicles==#task.expectedVehicles+1
if out.verified then
 local v=out.newVehicles[1]
 out.verified=not v.noPath and not v.userStopped and v.line==lineId and #v.models==1 and v.models[1]==task.model and out.result.bought[1]==v.id
end
return B.json.encode(out)
