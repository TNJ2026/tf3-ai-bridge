local p=api.type.SimpleProposal.new();local add={};local out={}
for _,n in ipairs({72647,70933,72653}) do
 assert(api.engine.getComponent(n,api.type.ComponentType.BASE_NODE_CONFIG)==nil,'configuration changed')
 local ids=api.engine.system.streetSystem.getNodeSegments(n);assert(#ids==3,'junction changed')
 local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=n;v.comp.trafficLightPreference=2
 local lanes={};for _,a in ipairs(ids) do for _,b in ipairs(ids) do if a~=b then local l=api.type.LaneConnection.new();l.segment0=a;l.lane0=1;l.segment1=b;l.lane1=#api.engine.getComponent(b,api.type.ComponentType.BASE_EDGE).laneConfigs-2;l.withRoad=true;l.withTram=false;lanes[#lanes+1]=l end end end
 v.comp.laneConnections=lanes;add[#add+1]=v
end
p.streetProposal.nodeConfigsToAdd=add
api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(r,ok)out.success=ok end)
return B.json.encode(out)
