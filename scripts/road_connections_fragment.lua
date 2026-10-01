-- Run after construction, separately from the original proposal. Replacing an edge
-- can change its id, so keep node pairs as the durable identity for this operation.
local function finishRoadConnections(endpoints, newEdges, before)
 local CT=api.type.ComponentType
 local pairsToFind={}
 for _,id in ipairs(newEdges) do local e=getComponent(id,'BASE_EDGE');if e then pairsToFind[#pairsToFind+1]={e.node0,e.node1} end end
 local function currentEdges()
  local out={};local seen={}
  for _,pair in ipairs(pairsToFind) do
   for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(pair[1]))) do
    local e=getComponent(id,'BASE_EDGE')
    if e and ((e.node0==pair[1] and e.node1==pair[2]) or (e.node1==pair[1] and e.node0==pair[2])) and not seen[id] then
     seen[id]=true;out[#out+1]=id
    end
   end
  end
  return out,seen
 end
 local function farNodes(edge,node,mode,incoming)
  local tn=getComponent(edge,'TRANSPORT_NETWORK');local out={}
  if tn then for _,e in ipairs(tn.edges) do if e.transportModes[mode] then
   local a,b=e.conns[1],e.conns[2]
   if incoming and a.entity~=node and b.entity==node then out[#out+1]=a end
   if not incoming and a.entity==node and b.entity~=node then out[#out+1]=b end
  end end end
  return out
 end
 local function check(node,newSet)
  local old,new={},{}
  for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do
   if newSet[id] then new[#new+1]=id else old[#old+1]=id end
  end
  if #new==0 or #old==0 then return false,'missing adjacent road' end
  if not api.engine.util.pathfinding then return false,'pathfinding unavailable' end
  for _,mode in ipairs({api.type.enum.TransportMode.CAR,api.type.enum.TransportMode.TRUCK}) do
   for _,a in ipairs(old) do for _,b in ipairs(new) do
    local x,y=farNodes(a,node,mode,true),farNodes(b,node,mode,false)
    local rx,ry=farNodes(b,node,mode,true),farNodes(a,node,mode,false)
    if #x==0 or #y==0 or #rx==0 or #ry==0 then return false,'vehicle lanes unavailable' end
    for _,direction in ipairs({{x,y},{rx,ry}}) do
     local route=api.engine.util.pathfinding.findPathNodeToNode(direction[1],direction[2],{mode})
     local usesOld,usesNew=false,false
     for _,step in ipairs(route) do
      local id=step[1].entity
      if id~=a and id~=b and id~=node then return false,'path detours through other roads' end
      usesOld=usesOld or id==a;usesNew=usesNew or id==b
     end
     if not usesOld or not usesNew then return false,'no direct two-way vehicle path' end
    end
   end end
  end
  return true
 end
 local out={verified=true,junctions={}}
 local visited={}
 for _,node in ipairs(endpoints) do if not visited[node] then
  visited[node]=true
  local _,newSet=currentEdges()
  local ok,why=check(node,newSet)
  local row={node=node,verified=ok,repaired=false}
  if not ok and why~='pathfinding unavailable' and why~='vehicle lanes unavailable' then
   local cfg=getComponent(node,'BASE_NODE_CONFIG')
   local canReset=before[node] and #before[node]==1 and cfg and #listOf(cfg.laneConnections)==0
   local reset=true
   if canReset then
    local p=api.type.SimpleProposal.new();p.streetProposal.nodeConfigsToRemove={node}
    reset=false;applyProposal(p,false,function(success) reset=success==true end)
   end
   if reset then
    for _,id in ipairs(listOf(api.engine.system.streetSystem.getNodeSegments(node))) do if newSet[id] then
     local success=false
     applyProposal(api.engine.util.proposal.replaceSegment(id),false,function(value) success=value==true end)
     row.repaired=success
     if not success then why='junction refresh rejected' end
     break
    end end
   else why='lane configuration reset rejected' end
   _,newSet=currentEdges()
   local checked,message=check(node,newSet);ok=checked;why=message or why
   row.verified=ok
  end
  if not ok then out.verified=false;row.reason=why end
  out.junctions[#out.junctions+1]=row
 end end
 out.edges=currentEdges()
 return out
end

