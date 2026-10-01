local p=api.type.SimpleProposal.new();p.streetProposal.edgeObjectsToRemove={76059}
local ok,pd=pcall(api.engine.util.proposal.makeProposalData,p,nil)
if not ok then return B.json.encode({ok=false,error=tostring(pd)}) end
return B.json.encode({ok=pd~=nil,critical=pd and pd.errorState.critical,messages=pd and B.toPlain(pd.errorState.messages),collisions=pd and B.toPlain(pd.collisionInfo.collisionEntities)})

