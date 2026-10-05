-- Preview-only PERSON graph, including automatic links at their actual edge parameters.
-- No world mutation. Existing roads are supplied by the road-first phase readback.
local CT=api.type.ComponentType
local nets={};for id,n in pairs(pd.entity2tn)do nets[id]=n end
for _,id in ipairs(spec.existingRoadEntities or{})do
 if not nets[id]then nets[id]=assert(api.engine.getComponent(id,CT.TRANSPORT_NETWORK),'Existing road network missing')end
end
local function nk(n)return tostring(n.entity)..':'..tostring(n.index)end
local function ek(e)return tostring(e.entity)..':'..tostring(e.index)end
local walkingEdges,starts,goals={},{},{}
for id,net in pairs(nets)do
 local bus,heli,person,car=false,false,false,false
 for _,e in ipairs(net.edges)do bus=bus or e.transportModes[3];heli=heli or e.transportModes[13];person=person or e.transportModes[0];car=car or e.transportModes[2]end
 for i,e in ipairs(net.edges)do if e.transportModes[0]then
  local key=tostring(id)..':'..tostring(i-1)
  walkingEdges[key]={a=nk(e.conns[1]),b=nk(e.conns[2]),reverse=not e.forwardOnly,points={}}
  if id<0 and person and not car then
   local target=bus and starts or heli and goals or nil
   if target then target[nk(e.conns[1])]=true;target[nk(e.conns[2])]=true end
  end
 end end
end
local graph={}
local function add(a,b)graph[a]=graph[a]or{};graph[a][b]=true end
local linkCount=0
local function attach(p)
 local key=ek(p.edgeId);local e=walkingEdges[key]
 if not e then return nil end
 local t=p.param;assert(t>=0 and t<=1,'Link parameter outside edge')
 if t<.000001 then return e.a end;if t>.999999 then return e.b end
 local node='link:'..key..':'..string.format('%.9f',t)
 e.points[#e.points+1]={t=t,node=node};return node
end
for _,r in ipairs(pd.tpNetLinkProposal.toAdd)do
 -- The live binding exposes a TpNetLink (from/to), despite the pair in type docs.
 local first,second=r.link.from,r.link.to
 assert(first and second,'Unreadable native pedestrian link')
 local a,b=attach(first),attach(second)
 if a and b then add(a,b);add(b,a);linkCount=linkCount+1 end
end
for _,e in pairs(walkingEdges)do
 table.sort(e.points,function(a,b)return a.t<b.t end)
 local last=e.a
 for _,p in ipairs(e.points)do add(last,p.node);if e.reverse then add(p.node,last)end;last=p.node end
 add(last,e.b);if e.reverse then add(e.b,last)end
end
local function reach(a,b)
 local q,seen={},{};for n in pairs(a)do q[#q+1]=n;seen[n]=true end
 local i=1;while i<=#q do local n=q[i];i=i+1;if b[n]then return true end
  for v in pairs(graph[n]or{})do if not seen[v]then seen[v]=true;q[#q+1]=v end end
 end;return false
end
local function count(t)local n=0;for _ in pairs(t)do n=n+1 end;return n end
local walkPreview={outbound=reach(starts,goals),inbound=reach(goals,starts),
 busNodes=count(starts),airportNodes=count(goals),automaticPersonLinks=linkCount,
 basis='Directed PERSON lanes plus bidirectional native automatic pedestrian links; native post-build pathfinding still required'}
