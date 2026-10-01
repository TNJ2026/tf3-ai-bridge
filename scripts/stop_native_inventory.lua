local CT=api.type.ComponentType
local out={objects={},stations={}}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(0,0),11000,CT.EDGE_OBJECT)) do
 local c=api.engine.getComponent(id,CT.EDGE_OBJECT)
 local r={id=id,param=c.param,resource=c.edgeObjectConstruction,params=B.toPlain(c.params),position=B.toPlain(c.transf:getTransl())}
 local ok,e=pcall(api.engine.system.streetSystem.getEdgeForEdgeObject,id);r.edge=ok and e or nil
 if r.edge and r.edge>=0 and api.engine.entityExists(r.edge) then local b=api.engine.getComponent(r.edge,CT.BASE_EDGE);r.refs=B.toPlain(b.objects) end
 out.objects[#out.objects+1]=r
end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(0,0),11000,CT.STATION)) do out.stations[#out.stations+1]={id=id,component=B.toPlain(api.engine.getComponent(id,CT.STATION))} end
return B.json.encode(out)

