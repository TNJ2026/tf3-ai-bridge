local task=B.json.decode(TASKJSON)
local CT=api.type.ComponentType
local out={verified=true,junctions={},edges={}}
local new={};for _,id in ipairs(task.edges)do assert(api.engine.getComponent(id,CT.BASE_EDGE),'road edge disappeared');new[id]=true;out.edges[#out.edges+1]=id end
local function far(id,node,mode,incoming)
 local net=api.engine.getComponent(id,CT.TRANSPORT_NETWORK);local rr={}
 if net then for _,e in ipairs(net.edges)do if e.transportModes[mode]then
  local a,b=e.conns[1],e.conns[2]
  if incoming and a.entity~=node and b.entity==node then rr[#rr+1]=a end
  if not incoming and a.entity==node and b.entity~=node then rr[#rr+1]=b end
 end end end
 return rr
end
for _,node in ipairs(task.nodes)do
 local row={node=node,verified=true,paths={}}
 for _,old in ipairs(api.engine.system.streetSystem.getNodeSegments(node))do if not new[old]then
  for _,branch in ipairs(api.engine.system.streetSystem.getNodeSegments(node))do if new[branch]then
   for _,mode in ipairs({api.type.enum.TransportMode.CAR,api.type.enum.TransportMode.TRUCK})do
    for _,pair in ipairs({{old,branch},{branch,old}})do
     local a,b=far(pair[1],node,mode,true),far(pair[2],node,mode,false)
     local path=api.engine.util.pathfinding.findPathNodeToNode(a,b,{mode});local ok=#a>0 and #b>0;local usesA,usesB=false,false;local steps={}
     for _,st in ipairs(path)do local id=st[1].entity;steps[#steps+1]=id;usesA=usesA or id==pair[1];usesB=usesB or id==pair[2];if id~=pair[1]and id~=pair[2]and id~=node then ok=false end end
     ok=ok and usesA and usesB;row.paths[#row.paths+1]={from=pair[1],to=pair[2],mode=mode,verified=ok,steps=steps};row.verified=row.verified and ok
    end
   end
  end end
 end end
 if #row.paths==0 then row.verified=false end
 out.verified=out.verified and row.verified;out.junctions[#out.junctions+1]=row
end
return B.json.encode(out)
