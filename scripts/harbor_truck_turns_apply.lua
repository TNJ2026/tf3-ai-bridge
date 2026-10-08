local CT=api.type.ComponentType;local node=70827;local branch=107444
local old=api.engine.getComponent(node,CT.BASE_NODE_CONFIG)
assert(old and not old.userModifiedTrafficLightStates and #old.crosswalks==0,'junction outside reviewed repair scope')
local branchEdge=api.engine.getComponent(branch,CT.BASE_EDGE)
assert(branchEdge and branchEdge.node1==node and branchEdge.node0==86037,'stale branch')
local adjacent={};for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(node)) do adjacent[#adjacent+1]={id=id,c=api.engine.getComponent(id,CT.BASE_EDGE)} end
assert(#adjacent==3,'junction changed')
local turns={};local rows={}
local function append(l)
 turns[#turns+1]=l;rows[#rows+1]={from=l.segment0,fromLane=l.lane0,to=l.segment1,toLane=l.lane1,road=l.withRoad,tram=l.withTram}
end
for _,l in ipairs(old.laneConnections) do assert(l.segment0~=branch and l.segment1~=branch,'branch turns already configured');append(l) end
local retained=#turns
for _,a in ipairs(adjacent) do for _,b in ipairs(adjacent) do if a.id~=b.id and (a.id==branch or b.id==branch) then
 for ka,la in ipairs(a.c.laneConfigs) do
  if ((a.c.node0==node and not la.forward) or (a.c.node1==node and la.forward)) and la.transportModes[api.type.enum.TransportMode.TRUCK] then
   for kb,lb in ipairs(b.c.laneConfigs) do
    if ((b.c.node0==node and lb.forward) or (b.c.node1==node and not lb.forward)) and lb.transportModes[api.type.enum.TransportMode.TRUCK] then
     local l=api.type.LaneConnection.new();l.segment0=a.id;l.segment1=b.id;l.lane0=a.c.node0==node and ka-1 or #a.c.laneConfigs-ka;l.lane1=b.c.node0==node and kb-1 or #b.c.laneConfigs-kb;l.withRoad=true;l.withTram=false;append(l)
    end
   end
  end
 end
end end end
local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=node;v.comp=old
v.comp.laneConnections=turns
local p=api.type.SimpleProposal.new();p.streetProposal.nodeConfigsToRemove={node};p.streetProposal.nodeConfigsToAdd={v}
local pd=api.engine.util.proposal.makeProposalData(p,nil)
local out={retained=retained,turns=rows,critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),collisions=#pd.collisionInfo.collisionEntities}
assert(not out.critical and #out.messages==0 and out.collisions==0,'repair preview rejected');api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(_,ok)out.applied=ok end);return B.json.encode(out)
