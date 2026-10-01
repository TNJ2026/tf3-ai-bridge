local CT=api.type.ComponentType
local out={state=B.commands.get_game_state({}),edges={},heights={}}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(1900,1200),3600,CT.BASE_EDGE)) do
 local e=api.engine.getComponent(id,CT.BASE_EDGE)
 out.edges[#out.edges+1]={id=id,a=B.toPlain(e.position0),b=B.toPlain(e.position1),kind=e.roadType}
end
for y=-1400,4000,100 do for x=-200,4000,100 do
 local p=api.type.Vec2f.new(x,y);out.heights[#out.heights+1]={x,y,api.engine.terrain.getHeightAt(p),api.engine.terrain.isOnWater(p)}
end end
out.template=B.toPlain(api.res.streetTemplateRep.get(api.res.streetTemplateRep.find('::/infrastructure/track/simple/simple.street_template')))
return B.json.encode(out)
