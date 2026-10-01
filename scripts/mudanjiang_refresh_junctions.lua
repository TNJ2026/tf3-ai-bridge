local out={}
for _,id in ipairs({24629,27242,76230}) do
 local p=api.engine.util.proposal.replaceSegment(id)
 api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(r,ok)out[#out+1]={edge=id,success=ok}end)
end
return B.json.encode(out)
