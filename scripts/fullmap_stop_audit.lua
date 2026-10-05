-- Resolve a stop-bearing road by both endpoint positions, not old entity IDs.
local task=B.json.decode(TASKJSON);local CT=api.type.ComponentType;local found={}
local function close(a,b)return math.abs(a.x-b.x)<.2 and math.abs(a.y-b.y)<.2 end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(task.position.x,task.position.y),200,CT.BASE_EDGE))do
 local e=api.engine.getComponent(id,CT.BASE_EDGE)
 if close(e.position0,task.edge_endpoints[1])and close(e.position1,task.edge_endpoints[2])then found[#found+1]={id=id,c=e}end
end
assert(#found==1,'stop road missing/changed/ambiguous');local e=found[1]
local out={edge=e.id,node0=e.c.node0,node1=e.c.node1,objects={},verified=false}
for _,ref in ipairs(e.c.objects)do
 local st=api.engine.getComponent(ref[1],CT.STATION);local tn=api.engine.getComponent(e.id,CT.TRANSPORT_NETWORK)
 local row={id=ref[1],verified=st~=nil and tn~=nil,terminals={},catchables={}}
 if st and tn then
  for _,t in ipairs(st.terminals)do
   local v=t.vehicleNodeId;local valid=v.entity==e.id and v.index>=0 and v.index<#tn.nodes and #t.personNodes>0 and t.cargoUnload
   row.verified=row.verified and valid;row.terminals[#row.terminals+1]={node={entity=v.entity,index=v.index},cargoUnload=t.cargoUnload,cargoLoad=t.cargoLoad}
  end
  for _,id in pairs(api.engine.system.catchmentAreaSystem.getStationCatchables(ref[1],true))do row.catchables[#row.catchables+1]=id end
 end
 out.objects[#out.objects+1]=row
end
out.verified=#out.objects==2
for _,o in ipairs(out.objects)do out.verified=out.verified and o.verified end
return B.json.encode(out)
