return function(args,B)
 local CT=api.type.ComponentType;local id=args.edge
 local old=api.engine.getComponent(id,CT.BASE_EDGE);assert(old and #old.objects==0,'road changed or already has stops')
 local p=api.type.SimpleProposal.new();local e=api.type.SegmentAndEntity.new();e.entity=-1;e.type=0;e.comp=old
 local se=api.engine.getComponent(id,CT.BASE_EDGE_STREET);if se then e.streetEdge=se end
 p.streetProposal.edgesToAdd={e};p.streetProposal.edgesToRemove={id}
 local eo=api.type.SimpleStreetProposal.EdgeObject.new();eo.edgeEntity=-1;eo.param=.5;eo.oneWay=false;eo.left=false
 eo.model='::/stations/street/small_stops/small_mid_twosided.con';eo.playerEntity=api.engine.util.getPlayer();eo.name=args.name
 p.streetProposal.edgeObjectsToAdd={eo}
 local configs={};local remove={}
 for _,n in ipairs({old.node0,old.node1}) do
  local c=api.engine.getComponent(n,CT.BASE_NODE_CONFIG);assert(c,'missing endpoint configuration')
  local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=n;v.comp=c
  local lanes={};for _,l in ipairs(c.laneConnections) do local t=api.type.LaneConnection.new();t.segment0=l.segment0==id and -1 or l.segment0;t.segment1=l.segment1==id and -1 or l.segment1;t.lane0=l.lane0;t.lane1=l.lane1;t.withRoad=l.withRoad;t.withTram=l.withTram;lanes[#lanes+1]=t end
  v.comp.laneConnections=lanes;configs[#configs+1]=v;remove[#remove+1]=n
 end
 p.streetProposal.nodeConfigsToAdd=configs;p.streetProposal.nodeConfigsToRemove=remove
 local pd=api.engine.util.proposal.makeProposalData(p,nil)
 local out={critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),cost=pd.costs,collisions={},built=false}
 for _,c in ipairs(pd.collisionInfo.collisionEntities) do out.collisions[#out.collisions+1]=c.entity end
 out.buildable=not out.critical and #out.collisions==0
 if args.apply then assert(out.buildable,'stop preview blocked');api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(r,ok)out.built=ok end) end
 return B.json.encode(out)
end
