local CT=api.type.ComponentType;local out={stations=B.commands.list_stations({}),depots=B.commands.list_depots({}),roads={},capacities={}}
for _,pair in ipairs({{62014,61589},{60819,61155},{60802,6798},{60810,60817},{61759,62477},{60812,60999}}) do
 for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(pair[1])) do local e=api.engine.getComponent(id,CT.BASE_EDGE);if e.node0==pair[2] or e.node1==pair[2] then
 local tn=api.engine.getComponent(id,CT.TRANSPORT_NETWORK);local r={id=id,node0=e.node0,node1=e.node1,objects=B.toPlain(e.objects),networkNodes=#tn.nodes,networkEdges=#tn.edges,configs={}}
 for _,n in ipairs(pair) do local c=api.engine.getComponent(n,CT.BASE_NODE_CONFIG);local lanes={};for _,l in ipairs(c.laneConnections) do lanes[#lanes+1]={segment0=l.segment0,segment1=l.segment1,lane0=l.lane0,lane1=l.lane1} end;r.configs[#r.configs+1]={id=n,crosswalks=B.toPlain(c.crosswalks),lanes=lanes} end
 out.roads[#out.roads+1]=r
 end end
end
local ok,ids=pcall(api.engine.getEntitiesWithComponent,CT.PERSON_CAPACITY);out.capacities.enumerable=ok
if ok then local map=api.engine.system.townBuildingSystem.getPersonCapacity2townBuildingMap();out.capacities.total=#ids;out.capacities.nonTown={};for _,id in ipairs(ids) do if not map[id] then local c=api.engine.getComponent(id,CT.PERSON_CAPACITY);out.capacities.nonTown[#out.capacities.nonTown+1]={id=id,type=c.type,capacity=c.capacity} end end end
out.game=B.commands.get_game_state()
return B.json.encode(out)
