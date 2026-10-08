local p=api.type.SimpleProposal.new();local remove={};local out={}
for _,n in ipairs({72647,70933,72653}) do
 local c=api.engine.getComponent(n,api.type.ComponentType.BASE_NODE_CONFIG)
 assert(c and #c.laneConnections==2 and not c.userModifiedTrafficLightStates and #c.crosswalks==0,'unexpected junction configuration')
 local a,b=c.laneConnections[1],c.laneConnections[2]
 assert(a.segment0==b.segment1 and a.segment1==b.segment0 and a.withRoad and b.withRoad,'non-default turn configuration')
 remove[#remove+1]=n
end
p.streetProposal.nodeConfigsToRemove=remove
api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(r,ok)out.success=ok end)
return B.json.encode(out)
