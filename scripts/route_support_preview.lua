-- Read-only: compatible purchase bases and endpoint maintenance; no route searches.
local tasks=B.json.decode(TASKJSON);local CT=api.type.ComponentType
local depots={};local out={lines={},depots={}}
api.engine.forEachEntityWithComponent(function(id)
 local c=api.engine.getComponent(id,CT.CONSTRUCTION);local p=c.transf:cols(3)
 for _,did in ipairs(c.depots)do
  local d=api.engine.getComponent(did,CT.VEHICLE_DEPOT)
  if d then
   local row={construction=id,depot=did,x=p.x,y=p.y,pool=d.maintenancePool,radius=d.catchmentArea and d.catchmentArea.radius,modes={}}
   for _,name in ipairs({'TRUCK','HELICOPTER','SMALL_SHIP'})do if d.transportModes[api.type.enum.TransportMode[name]]then row.modes[#row.modes+1]=name end end
   if #row.modes>0 then depots[#depots+1]={data=d,row=row};out.depots[#out.depots+1]=row end
  end
 end
end,CT.CONSTRUCTION)
for _,t in ipairs(tasks)do
 local mode=api.type.enum.TransportMode[t.mode];local s=t.stops[1]
 for _,stop in ipairs(t.stops)do
  local group=assert(api.engine.getComponent(stop.group,CT.STATION_GROUP),'group missing')
  local station=assert(api.engine.getComponent(group.stations[stop.station+1],CT.STATION),'station missing')
  assert(station.terminals[stop.terminal+1],'terminal missing')
 end
 local row={id=t.id,purchaseCandidates={},maintenanceCandidates={},pathVerified=false,maintenanceScope='endpoint coverage only; absence does not prove no maintenance'}
 for _,v in ipairs(depots)do
  local d=v.data
  if d.transportModes[mode]then
   if #d.outNodes>0 then row.purchaseCandidates[#row.purchaseCandidates+1]=v.row end
   if d.maintenancePool and d.maintenancePool>0 and d.catchmentArea then
    local p=d.catchmentArea.position;local radius=d.catchmentArea.radius;local covered={}
    for i,point in ipairs(t.positions)do if (point.x-p.x)^2+(point.y-p.y)^2<=radius^2 then covered[#covered+1]=i end end
    if #covered>0 then row.maintenanceCandidates[#row.maintenanceCandidates+1]={depot=v.row.depot,construction=v.row.construction,pool=d.maintenancePool,radius=radius,coveredEndpoints=covered}end
   end
  end
 end
 out.lines[#out.lines+1]=row
end
return B.json.encode(out)
