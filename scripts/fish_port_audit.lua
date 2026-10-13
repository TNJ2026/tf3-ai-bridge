-- Independent, read-only acceptance. Does not create lines, buy ships or alter terrain.
local spec=B.json.decode(SPEC_JSON);local origin=B.json.decode(ORIGIN_JSON);local added=B.json.decode(ADDED_JSON)
local CT=api.type.ComponentType;local angle=math.rad(origin.rotation);local roles={};local cs={}
local out={facilities={},paths={},coverage={},service={},staticAccepted=false,operationalAccepted=false,
 pending={'actual departure, normal line operation, no native fault'}}
assert(#added.constructions==#spec.facilities,'Unexpected construction count')
for _,f in ipairs(spec.facilities)do
 local x=origin.x+f.localPosition.x*math.cos(angle)-f.localPosition.y*math.sin(angle)
 local y=origin.y+f.localPosition.x*math.sin(angle)+f.localPosition.y*math.cos(angle)
 local matches={}
 for _,id in ipairs(added.constructions)do
  local c=assert(api.engine.getComponent(id,CT.CONSTRUCTION),'Construction missing');local p=c.transf:cols(3)
  if c.fileName==f.resource and math.abs(p.x-x)<.2 and math.abs(p.y-y)<.2 then matches[#matches+1]={id=id,c=c}end
 end
 assert(#matches==1,'Missing/ambiguous role '..f.role);local row=matches[1];roles[f.role]=row.id;cs[f.role]=row.c
 local a=angle+math.rad(f.relativeRotation);local v=row.c.transf:cols(0)
 assert(math.abs(v.x-math.cos(a))<.002 and math.abs(v.y-math.sin(a))<.002,'Rotation mismatch')
 local count,wanted=0,0
 for slot,m in pairs(row.c.params.modules or{})do
  count=count+1;local e=f.params.modules[tostring(slot)]or f.params.modules[slot]
  assert(e and e.name==m.name and (e.variant or 0)==(m.variant or 0),'Module mismatch')
 end
 for _ in pairs(f.params.modules or{})do wanted=wanted+1 end
 assert(count==wanted,'Module count mismatch')
 local owner=assert(api.engine.getComponent(row.id,CT.PLAYER_OWNED),'Missing ownership')
 assert(owner.player==api.engine.util.getPlayer(),'Owner mismatch')
 out.facilities[f.role]={entity=row.id,modulesVerified=true,poseVerified=true}
end
local stationRoles=roles.truck and {'harbor','truck'}or{'harbor','helipad','helipad2'}
local targets={};for _,role in ipairs(stationRoles)do targets[role]=assert(roles[role],'Missing cargo station role')end
local shared=primaryWarehouse(roles.warehouse,targets,spec.primaryStockList)
out.sharedWarehouse=shared;out.coverage=shared.coverage
local common=shared.commonWarehouseStockIds
out.commonWarehouseStockIds=common
local transportAccepted=false
if roles.truck then
local internal={};for _,id in ipairs(cs.truck.frozenEdges)do internal[id]=true end
local roads={}
for _,id in ipairs(added.edges)do
 local edge=assert(api.engine.getComponent(id,CT.BASE_EDGE),'Missing road')
 assert(api.engine.getComponent(id,CT.TRANSPORT_NETWORK),'Road network missing')
 assert(api.engine.getComponent(edge.node0,CT.TRANSPORT_NETWORK)and api.engine.getComponent(edge.node1,CT.TRANSPORT_NETWORK),'Endpoint network missing')
 if not internal[id]then roads[#roads+1]=id end
end
local mode=api.type.enum.TransportMode.TRUCK
local function nodes(ids)
 local out={}
 for _,id in ipairs(ids)do local net=api.engine.getComponent(id,CT.TRANSPORT_NETWORK)
  if net then for _,e in ipairs(net.edges)do if e.transportModes[mode]then out[#out+1]=e.conns[1];out[#out+1]=e.conns[2]end end end
 end
 return out
end
local a,b=nodes(cs.truck.stations),nodes(roads)
out.paths.truck={outbound=false,inbound=false}
if #a>0 and #b>0 then
 out.paths.truck.outbound=#api.engine.util.pathfinding.findPathNodeToNode(a,b,{mode})>0
 out.paths.truck.inbound=#api.engine.util.pathfinding.findPathNodeToNode(b,a,{mode})>0
end
transportAccepted=out.paths.truck.outbound and out.paths.truck.inbound
else
 -- Both separate pads must share the SAME warehouse inventory with the harbor.
 -- Actual terminal allocation and routes are checked when lines are authorized.
 out.transferMode='helicopter';out.paths.airRoutes='not_configured'
 transportAccepted=roles.helipad~=roles.helipad2 and #out.coverage.helipad>0 and #out.coverage.helipad2>0
end
local service=false
for _,id in ipairs(cs.water_maintenance.depots)do
 local d=api.engine.getComponent(id,CT.VEHICLE_DEPOT)
 if d then
  local compatible=d.transportModes[api.type.enum.TransportMode.SHIP]and d.transportModes[api.type.enum.TransportMode.SMALL_SHIP]
  local radius=d.catchmentArea and d.catchmentArea.radius
  local p=d.catchmentArea and d.catchmentArea.position;local berth=cs.harbor.transf:cols(3)
  local covers=p and radius and (p.x-berth.x)^2+(p.y-berth.y)^2<radius^2
  out.service[#out.service+1]={entity=id,pool=d.maintenancePool,radius=radius,shipModes=compatible,harborWithinRadius=covers}
  service=service or (compatible and covers and d.maintenancePool>0)
 end
end
-- Ship route diagnostics are opt-in, not infrastructure acceptance gates.
out.purchase={required=roles.water_depot~=nil,harborPathsVerified=false,purchaseExecuted=false}
out.infrastructureAccepted=#common>0 and transportAccepted and service
out.staticAccepted=false
return B.json.encode(out)
