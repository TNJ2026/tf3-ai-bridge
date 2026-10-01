local CT=api.type.ComponentType;local out={routes={},forest={}}
local function lanes(node,mode)
 local o={};for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(node)) do local t=api.engine.getComponent(id,CT.TRANSPORT_NETWORK);for _,e in ipairs(t.edges) do if e.transportModes[mode] then for _,c in ipairs(e.conns) do if c.entity==node then o[#o+1]=c end end end end end;return o
end
for _,m in ipairs({api.type.enum.TransportMode.TRUCK,api.type.enum.TransportMode.CAR}) do for _,ends in ipairs({{76238,48615},{48615,76238}}) do
 local path=api.engine.util.pathfinding.findPathNodeToNode(lanes(ends[1],m),lanes(ends[2],m),{m});local seen={};local d=0
 for _,s in ipairs(path) do local id=s[1].entity;if not seen[id] then seen[id]=true;local e=api.engine.getComponent(id,CT.BASE_EDGE);if e then local a,b=e.position0,e.position1;d=d+math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end end end
 out.routes[#out.routes+1]={mode=m,from=ends[1],to=ends[2],found=#path>0,steps=#path,roadLength=d}
end end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(568,-1600),30,CT.CONSTRUCTION)) do local c=api.engine.getComponent(id,CT.CONSTRUCTION);if c.fileName=='::/industries/forest/forest.con' then for _,i in ipairs(c.industries) do local ind=api.engine.getComponent(i,CT.INDUSTRY);out.forest={construction=id,industry=i,capacity=api.engine.util.stock.getCargoMaxProductionPerYear(ind.stockList,12)} end end end
local ok,r=pcall(api.engine.util.town.computeTownsTrafficSpeedMap,1);out.trafficSpeedCalculation={success=ok};if not ok then out.trafficSpeedCalculation.error=tostring(r) end
out.state=B.commands.get_game_state({})
return B.json.encode(out)
