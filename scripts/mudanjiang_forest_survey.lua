local CT=api.type.ComponentType
local c=api.engine.getComponent(48636,CT.CONSTRUCTION)
local out={state=B.commands.get_game_state({}),forest=B.toPlain(c),sites={}}
for _,p in ipairs({{168,-1600},{568,-1600},{1168,-1600},{-480,-700}}) do
 local row={x=p[1],y=p[2],heights={},water=false,near={}}
 for x=p[1]-250,p[1]+250,50 do for y=p[2]-250,p[2]+250,50 do local q=api.type.Vec2f.new(x,y);row.heights[#row.heights+1]=api.engine.terrain.getHeightAt(q);if api.engine.terrain.isOnWater(q) then row.water=true end end end
 for _,k in ipairs({'TOWN_BUILDING','CONSTRUCTION','BASE_EDGE'}) do row.near[k]=B.toPlain(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(p[1],p[2]),300,CT[k])) end
 out.sites[#out.sites+1]=row
end
return B.json.encode(out)
