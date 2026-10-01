local CT=api.type.ComponentType;local out={};local p=api.type.SimpleProposal.new();local remove={}
for _,n in ipairs({56774,58679}) do if api.engine.getComponent(n,CT.BASE_NODE_CONFIG) then remove[#remove+1]=n end end
if #remove>0 then p.streetProposal.nodeConfigsToRemove=remove;api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(r,ok) out.removed=ok end) end
out.refresh={}
for _,n in ipairs({56774,58679}) do
 for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(n)) do
  local e=api.engine.getComponent(id,CT.BASE_EDGE)
  if e.roadTemplate=='::/infrastructure/street/country/country_old_medium.street_template' then
   local q=api.engine.util.proposal.replaceSegment(id)
   api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(q,nil,false,true),function(r,ok) out.refresh[#out.refresh+1]={edge=id,success=ok} end)
   break
  end
 end
end
return B.json.encode(out)
