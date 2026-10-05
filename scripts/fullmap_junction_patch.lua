-- Restricted three-way junction repair. Preserve existing turns/crosswalks/signals.
local CT=api.type.ComponentType
local task=B.json.decode(TASKJSON)
local apply=APPLY
local node,branch=task.node,task.branch
local n=api.engine.getComponent(node,CT.BASE_NODE)
assert(n and math.abs(n.position.x-task.x)<.2 and math.abs(n.position.y-task.y)<.2,'junction moved')
local oldCount=#task.existingEdges;assert(oldCount==2 or oldCount==3,"unsupported degree")
local cfg=api.engine.getComponent(node,CT.BASE_NODE_CONFIG)
assert(cfg and not cfg.userModifiedTrafficLightStates and #cfg.laneConnections==oldCount*(oldCount-1) and #cfg.crosswalks<=oldCount,'unexpected original junction configuration')
local known={};for _,e in ipairs(task.existingEdges)do known[e]=true end
for _,crosswalk in ipairs(cfg.crosswalks)do assert(known[crosswalk],'unexpected crosswalk')end
local edges={}
for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(node))do
 assert(known[id]or id==branch,'junction has unrelated road')
 local c=api.engine.getComponent(id,CT.BASE_EDGE);assert(c and #c.laneConfigs==4,'unexpected lane layout');edges[#edges+1]={id=id,c=c}
end
assert(#edges==oldCount+1,'expected one added branch')
local turns={}
for _,l in ipairs(cfg.laneConnections)do assert(known[l.segment0]and known[l.segment1],'original turns changed');turns[#turns+1]=l end
local rows={}
for _,a in ipairs(edges)do for _,b in ipairs(edges)do if a.id~=b.id and(a.id==branch or b.id==branch)then
 for ka,la in ipairs(a.c.laneConfigs)do
  if((a.c.node0==node and not la.forward)or(a.c.node1==node and la.forward))and la.transportModes[api.type.enum.TransportMode.TRUCK]then
   for kb,lb in ipairs(b.c.laneConfigs)do
    if((b.c.node0==node and lb.forward)or(b.c.node1==node and not lb.forward))and lb.transportModes[api.type.enum.TransportMode.TRUCK]then
     local l=api.type.LaneConnection.new();l.segment0=a.id;l.segment1=b.id;l.lane0=a.c.node0==node and ka-1 or #a.c.laneConfigs-ka;l.lane1=b.c.node0==node and kb-1 or #b.c.laneConfigs-kb;l.withRoad=true;l.withTram=false;turns[#turns+1]=l;rows[#rows+1]={from=l.segment0,to=l.segment1,lane0=l.lane0,lane1=l.lane1}
    end
   end
  end
 end
end end end
assert(#rows==2*oldCount,'expected exactly four additional turns')
local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=node;v.comp=cfg;v.comp.laneConnections=turns
local p=api.type.SimpleProposal.new();p.streetProposal.nodeConfigsToRemove={node};p.streetProposal.nodeConfigsToAdd={v}
local pd=api.engine.util.proposal.makeProposalData(p,nil)
local out={critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),collisions=B.toPlain(pd.collisionInfo.collisionEntities),retainedTurns=oldCount*(oldCount-1),retainedCrosswalks=#cfg.crosswalks,addedTurns=rows}
assert(not out.critical and #out.messages==0 and #out.collisions==0,'junction proposal blocked')
if apply then api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(_,ok)out.applied=ok==true end)end
return B.json.encode(out)
