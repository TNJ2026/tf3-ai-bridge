local CT=api.type.ComponentType;local mode=api.type.enum.TransportMode.TRUCK
local function lanes(id,node,incoming)
 local tn=api.engine.getComponent(id,CT.TRANSPORT_NETWORK);local out={}
 for _,e in ipairs(tn.edges) do if e.transportModes[mode] then local a,b=e.conns[1],e.conns[2];if incoming and a.entity~=node and b.entity==node then out[#out+1]=a elseif not incoming and a.entity==node and b.entity~=node then out[#out+1]=b end end end
 return out
end
local out={}
for _,n in ipairs({72647,70933,72653,75674}) do
 local ids=api.engine.system.streetSystem.getNodeSegments(n);local row={node=n,checks={}}
 for _,a in ipairs(ids) do for _,b in ipairs(ids) do if a~=b then
 local path=api.engine.util.pathfinding.findPathNodeToNode(lanes(a,n,true),lanes(b,n,false),{mode});local direct=#path>0
 for _,s in ipairs(path) do if s[1].entity~=a and s[1].entity~=b and s[1].entity~=n then direct=false end end
 row.checks[#row.checks+1]={from=a,to=b,steps=#path,direct=direct}
 end end end;out[#out+1]=row
end
return B.json.encode(out)
