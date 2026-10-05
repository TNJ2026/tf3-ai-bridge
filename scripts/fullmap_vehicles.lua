local task=B.json.decode(TASKJSON);local action=ACTION;local CT=api.type.ComponentType
local lineId
for _,id in ipairs(api.engine.system.lineSystem.getLines())do local n=api.engine.getComponent(id,CT.NAME);if n and n.name==task.name then assert(not lineId,'duplicate line');lineId=id end end
assert(lineId,'line missing');local line=api.engine.getComponent(lineId,CT.LINE)
local function node(s)local g=api.engine.getComponent(s.stationGroup,CT.STATION_GROUP);return api.engine.getComponent(g.stations[s.station+1],CT.STATION).terminals[s.terminal+1].vehicleNodeId end
local first=node(line.stops[1]);local mode=api.type.enum.TransportMode[task.mode]
local function vehicles()
 local out={};for _,id in ipairs(api.engine.system.transportVehicleSystem.getLineVehicles(lineId))do local v=api.engine.getComponent(id,CT.TRANSPORT_VEHICLE);out[#out+1]={id=id,line=v.line,noPath=v.noPath,depot=v.depot,state=v.state,userStopped=v.userStopped,stopIndex=v.stopIndex}end;return out
end
local out={line=lineId,vehicles=vehicles(),mode=task.mode}
if #out.vehicles>0 then out.existing=true;return B.json.encode(out)end
if action=='verify'then return B.json.encode(out)end
local candidates={}
api.engine.forEachEntityWithComponent(function(id)local c=api.engine.getComponent(id,CT.CONSTRUCTION);local p=c.transf:cols(3)
 for _,wanted in ipairs(task.depots)do if (task.mode~='SMALL_SHIP' or wanted.id==string.gsub(task.id,'_ship$','_shipyard'))and math.abs(p.x-wanted.position.x)<.2 and math.abs(p.y-wanted.position.y)<.2 then
  for _,dep in ipairs(c.depots)do local d=api.engine.getComponent(dep,CT.VEHICLE_DEPOT)
   if d and d.transportModes[mode]then
    local parked=#api.engine.system.transportVehicleSystem.getDepotVehicles(dep)
    local a=api.engine.util.pathfinding.findPathNodeToNode(d.outNodes,{first},{mode});local back=api.engine.util.pathfinding.findPathNodeToNode({first},d.inNodes,{mode})
    if #a>0 and #back>0 and (task.mode~='HELICOPTER'or parked<5)then
     local dist=0;for _,s in ipairs(a)do dist=dist+api.engine.getComponent(s[1].entity,CT.TRANSPORT_NETWORK).edges[s[1].index+1].geometry.length end
     candidates[#candidates+1]={depot=dep,facility=wanted.id,distance=dist,parked=parked,returnPath=true}
    end
   end
  end
 end end
end,CT.CONSTRUCTION)
assert(#candidates>0,'no reachable purchase depot with free parking');table.sort(candidates,function(a,b)return a.distance<b.distance end);out.selected=candidates[1]
local m=api.res.modelRep.find(task.model);assert(m>=0,'model missing');out.model=task.model
if action~='build'then return B.json.encode(out)end
B.commands.buy_vehicles({depot=out.selected.depot,model=task.model,count=1,line=lineId},function(ok,r)out.accepted=ok;out.result=r end)
out.vehicles=vehicles();out.verified=#out.vehicles==1 and out.vehicles[1].line==lineId and not out.vehicles[1].noPath
return B.json.encode(out)
