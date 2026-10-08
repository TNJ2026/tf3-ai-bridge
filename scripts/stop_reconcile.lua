local CT=api.type.ComponentType;local out={oldExists=api.engine.entityExists(62116),roads={},objects={},stations={}}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(1028,-53),160,CT.BASE_EDGE)) do local e=api.engine.getComponent(id,CT.BASE_EDGE);out.roads[#out.roads+1]={id=id,node0=e.node0,node1=e.node1,objects=B.toPlain(e.objects)} end
for _,kind in ipairs({'EDGE_OBJECT','STATION'}) do for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(1028,-53),200,CT[kind])) do out[kind=='STATION' and 'stations' or 'objects'][#out[kind=='STATION' and 'stations' or 'objects']+1]={id=id,comp=B.toPlain(api.engine.getComponent(id,CT[kind]))} end end
return B.json.encode(out)
