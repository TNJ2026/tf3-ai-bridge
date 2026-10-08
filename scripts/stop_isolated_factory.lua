return function(args,B)
 local CT=api.type.ComponentType;local id=args.edge
 local old=api.engine.getComponent(id,CT.BASE_EDGE);assert(old and #old.objects==0,'road changed or already has stops')
 local p=api.type.SimpleProposal.new();local e=api.type.SegmentAndEntity.new();e.entity=-1;e.type=0;e.comp=old
 local se=api.engine.getComponent(id,CT.BASE_EDGE_STREET);if se then e.streetEdge=se end
 p.streetProposal.edgesToAdd={e};p.streetProposal.edgesToRemove={id}
 local eo=api.type.SimpleStreetProposal.EdgeObject.new();eo.edgeEntity=-1;eo.param=.5;eo.oneWay=false;eo.left=false
 eo.model='::/stations/street/small_stops/small_mid_twosided.con';eo.playerEntity=api.engine.util.getPlayer();eo.name=args.name
 p.streetProposal.edgeObjectsToAdd={eo}
 eo.params={year=1960,seed=1}
 local pd=api.engine.util.proposal.makeProposalData(p,nil)
 if not pd then return B.json.encode({buildable=false,reason="nil proposal"}) end
 local out={critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),cost=pd.costs,collisions={},built=false}
 for _,c in ipairs(pd.collisionInfo.collisionEntities) do out.collisions[#out.collisions+1]=c.entity end
 out.buildable=not out.critical and #out.collisions==0
 if args.apply then assert(out.buildable,'stop preview blocked');api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(r,ok)out.built=ok end) end
 return B.json.encode(out)
end
