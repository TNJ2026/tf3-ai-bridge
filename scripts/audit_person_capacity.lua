local CT=api.type.ComponentType
local out={checkedBuildings=0,checkedCapacities=0,checkedNodes=0,issues={},orphans={},stationCount=0}
local function issue(kind,owner,details)out.issues[#out.issues+1]={kind=kind,owner=owner,details=details} end
local function checkNode(owner,n,role)
 out.checkedNodes=out.checkedNodes+1
 if not api.engine.entityExists(n.entity) then issue('missing_node_entity',owner,{entity=n.entity,index=n.index,role=role});return end
 local tn=api.engine.getComponent(n.entity,CT.TRANSPORT_NETWORK)
 if not tn then issue('missing_transport_network',owner,{entity=n.entity,index=n.index,role=role});return end
 if n.index<0 or n.index>=#tn.nodes then issue('node_index_out_of_range',owner,{entity=n.entity,index=n.index,count=#tn.nodes,role=role}) end
end
local caps={}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(0,0),11000,CT.TOWN_BUILDING)) do
 local b=api.engine.getComponent(id,CT.TOWN_BUILDING);out.checkedBuildings=out.checkedBuildings+1
 local pc=b.personCapacity
 if not api.engine.entityExists(pc) then issue('missing_person_capacity_entity',id,{entity=pc}) else
 local c=api.engine.getComponent(pc,CT.PERSON_CAPACITY)
 if not c then issue('missing_person_capacity_component',id,{entity=pc}) elseif not caps[pc] then
 caps[pc]=true;out.checkedCapacities=out.checkedCapacities+1
 if c.type~=0 and c.type~=1 and c.type~=2 then issue('invalid_land_use',pc,{value=c.type}) end
 for _,n in ipairs(c.personNodes) do checkNode(pc,n,'person') end
 for _,n in ipairs(c.vehicleNodes) do checkNode(pc,n,'vehicle') end
 end end
end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(0,0),11000,CT.STATION)) do
 out.stationCount=out.stationCount+1
 local s=api.engine.getComponent(id,CT.STATION)
 for _,t in ipairs(s.terminals) do
 if t.vehicleNodeId.entity>=0 then checkNode(id,t.vehicleNodeId,'terminal_vehicle') end
 for _,n in ipairs(t.personNodes) do checkNode(id,n,'terminal_person') end
 end
end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(0,0),11000,CT.EDGE_OBJECT)) do
 local e=api.engine.system.streetSystem.getEdgeForEdgeObject(id)
 if e<0 or not api.engine.entityExists(e) then out.orphans[#out.orphans+1]=id;issue('orphan_edge_object',id,{edge=e}) end
end
out.game=B.commands.get_game_state();out.vehicles=B.commands.list_vehicles({});out.ok=#out.issues==0
return B.json.encode(out)
