local CT=api.type.ComponentType;local o={}
for _,n in ipairs({56774,58679}) do local ids=api.engine.system.streetSystem.getNodeSegments(n);local sets={};local row={node=n,edges={ids[1],ids[2]},lanes={}}
for _,id in ipairs(ids) do local arr={};local tn=api.engine.getComponent(id,CT.TRANSPORT_NETWORK);for _,e in ipairs(tn.edges) do if e.transportModes[4] then for _,c in ipairs(e.conns) do row.lanes[#row.lanes+1]={entity=c.entity,index=c.index};if c.entity~=n then arr[#arr+1]=c end end end end;sets[#sets+1]=arr end
local p=api.engine.util.pathfinding.findPathNodeToNode(sets[1],sets[2],{api.type.enum.TransportMode.TRUCK});row.path={};for _,s in ipairs(p) do row.path[#row.path+1]={entity=s[1].entity,index=s[1].index} end;o[#o+1]=row end
return B.json.encode(o)
