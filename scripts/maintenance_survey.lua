local CT=api.type.ComponentType;local out={state=B.commands.get_game_state({}),map=B.commands.get_map_info({}),vehicles={},depots={},areas={}}
for _,id in ipairs(api.engine.getEntitiesWithComponent(CT.TRANSPORT_VEHICLE,{requireOwnedByPlayer=api.engine.util.getPlayer()}))do
 local v=api.engine.getComponent(id,CT.TRANSPORT_VEHICLE);local sum,change=0,0;local parts={}
 for _,p in ipairs(v.transportVehicleConfig.vehicles)do sum=sum+p.maintenanceState;change=change+p.maintenanceChange;parts[#parts+1]=api.res.modelRep.getName(p.part.modelId)end
 local n=api.engine.getComponent(v.line,CT.NAME)
 out.vehicles[#out.vehicles+1]={id=id,line=v.line,lineName=n and n.name,noPath=v.noPath,userStopped=v.userStopped,maintenanceStation=v.maintenanceStation,state=v.state,condition=sum/#parts,change=change/#parts,models=parts}
end
for _,id in ipairs(api.engine.getEntitiesWithComponent(CT.VEHICLE_DEPOT))do
 local d=api.engine.getComponent(id,CT.VEHICLE_DEPOT);local a=d.catchmentArea
 out.depots[#out.depots+1]={id=id,pool=d.maintenancePool,maxUsage=d.maxPoolUsage,averageUsage=d.averagePoolUsage,poolUsageTicks=d.poolUsageTicks,modes=B.toPlain(d.transportModes),radius=a and a.radius,position=a and {x=a.position.x,y=a.position.y,z=a.position.z}}
end
for _,t in ipairs(B.json.decode(TARGETS))do
 local area={id=t.id,center=t.position,roads={},obstacles={},constructions={}}
 for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(t.position.x,t.position.y),500,CT.BASE_EDGE))do
  local e=api.engine.getComponent(id,CT.BASE_EDGE)
  if e.roadType==api.type.enum.RoadType.STREET then area.roads[#area.roads+1]={id=id,node0=e.node0,node1=e.node1,p0={x=e.position0.x,y=e.position0.y},p1={x=e.position1.x,y=e.position1.y},t0={x=e.tangent0.x,y=e.tangent0.y},t1={x=e.tangent1.x,y=e.tangent1.y}}end
 end
 local seen={}
 for _,kind in ipairs({'CONSTRUCTION','MODEL_INSTANCE_LIST','TOWN_BUILDING','BASE_EDGE'})do
  for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(t.position.x,t.position.y),500,CT[kind]))do
   if not seen[id]then seen[id]=true
    local bv=api.engine.getComponent(id,CT.BOUNDING_VOLUME)
    if bv then area.obstacles[#area.obstacles+1]={id=id,kind=kind,min={x=bv.bbox.min.x,y=bv.bbox.min.y},max={x=bv.bbox.max.x,y=bv.bbox.max.y}}end
    local c=api.engine.getComponent(id,CT.CONSTRUCTION)
    if c then local q=c.transf:cols(3);area.constructions[#area.constructions+1]={id=id,resource=c.fileName,position={x=q.x,y=q.y,z=q.z}}end
   end
  end
 end
 out.areas[#out.areas+1]=area
end
return B.json.encode(out)
