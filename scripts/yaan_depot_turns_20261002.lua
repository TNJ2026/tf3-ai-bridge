local APPLY=false -- Task-specific: preview default; live IDs must match guards.
local C=api.type.ComponentType
local node,branch=58997,81454
local cfg=api.engine.getComponent(node,C.BASE_NODE_CONFIG)
assert(cfg and not cfg.userModifiedTrafficLightStates and #cfg.laneConnections==2 and #cfg.crosswalks==1 and cfg.crosswalks[1]==58998,"junction changed")
local b=api.engine.getComponent(branch,C.BASE_EDGE)
assert(b and b.node0==81445 and b.node1==node,"branch changed")
local edges={}
for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(node)) do assert(id==branch or id==58998 or id==76497,"unexpected road");edges[#edges+1]={id=id,c=api.engine.getComponent(id,C.BASE_EDGE)} end
assert(#edges==3,"junction changed")
local turns={}
for _,l in ipairs(cfg.laneConnections) do assert(l.segment0~=branch and l.segment1~=branch,"already repaired");turns[#turns+1]=l end
local rows={}
for _,a in ipairs(edges) do for _,b in ipairs(edges) do if a.id~=b.id and (a.id==branch or b.id==branch) then
 for ka,la in ipairs(a.c.laneConfigs) do
  if ((a.c.node0==node and not la.forward) or (a.c.node1==node and la.forward)) and la.transportModes[api.type.enum.TransportMode.TRUCK] then
   for kb,lb in ipairs(b.c.laneConfigs) do
    if ((b.c.node0==node and lb.forward) or (b.c.node1==node and not lb.forward)) and lb.transportModes[api.type.enum.TransportMode.TRUCK] then
     local l=api.type.LaneConnection.new();l.segment0=a.id;l.segment1=b.id;l.lane0=a.c.node0==node and ka-1 or #a.c.laneConfigs-ka;l.lane1=b.c.node0==node and kb-1 or #b.c.laneConfigs-kb;l.withRoad=true;l.withTram=false;turns[#turns+1]=l;rows[#rows+1]={from=l.segment0,to=l.segment1,fromLane=l.lane0,toLane=l.lane1}
    end
   end
  end
 end
end end end
assert(#rows==4,"unexpected lane count")
local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=node;v.comp=cfg;v.comp.laneConnections=turns
local p=api.type.SimpleProposal.new();p.streetProposal.nodeConfigsToRemove={node};p.streetProposal.nodeConfigsToAdd={v}
local pd=api.engine.util.proposal.makeProposalData(p,nil)
local messages={};for _,m in ipairs(pd.errorState.messages) do messages[#messages+1]=tostring(m) end
local out={retained=2,added=rows,crosswalksRetained=1,critical=pd.errorState.critical,messages=messages,collisions=#pd.collisionInfo.collisionEntities}
if APPLY then assert(not out.critical and #messages==0 and out.collisions==0,"repair preview rejected");api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(_,ok)out.applied=ok end) end
return out
