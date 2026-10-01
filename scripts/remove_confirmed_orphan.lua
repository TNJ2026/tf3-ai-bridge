local CT=api.type.ComponentType;assert(api.engine.entityExists(76059),'already removed');assert(api.engine.getComponent(76059,CT.EDGE_OBJECT),'not an edge object');assert(api.engine.system.streetSystem.getEdgeForEdgeObject(76059)<0,'object is no longer orphaned');assert(not api.engine.getComponent(76059,CT.STATION),'has station; refuse orphan cleanup')
local p=api.type.SimpleProposal.new();p.streetProposal.edgeObjectsToRemove={76059}
local pd=api.engine.util.proposal.makeProposalData(p,nil);assert(pd and not pd.errorState.critical and #pd.collisionInfo.collisionEntities==0,'removal blocked')
local accepted=false;api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(_,ok)accepted=ok end)
return B.json.encode({accepted=accepted,removed=not api.engine.entityExists(76059)})
