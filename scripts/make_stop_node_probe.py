import json
from pathlib import Path
base=Path('scripts/stop_crosswalk_factory.lua').read_text()
base=base[:base.index(' local pd=')]
base=base.replace(' p.streetProposal.edgesToAdd={e};p.streetProposal.edgesToRemove={id}', ''' if args.ref then e.comp.objects={{args.ref,api.type.enum.EdgeObjectType.STOP_RIGHT}} end
 p.streetProposal.edgesToAdd={e};p.streetProposal.edgesToRemove={id}''')
base+='''
 local ok,pd=pcall(api.engine.util.proposal.makeProposalData,p,nil)
 if not ok then return {error=tostring(pd)} end
 if not pd then return {error='nil proposal'} end
 local out={critical=pd.errorState.critical,networks={}}
 for id,tn in pairs(pd.entity2tn) do local ns={};for i,n in ipairs(tn.nodes) do ns[#ns+1]=B.toPlain(n) end;out.networks[tostring(id)]={nodes=#tn.nodes,edges=#tn.edges,details=ns} end
 return out
end
'''
Path('scripts/stop_node_preview.lua').write_text('local f=assert(load('+json.dumps(base)+',"=stopnodes","t",_ENV))();local out={};for _,r in ipairs({0,-1,-2,-3}) do out[tostring(r)]=f({edge=61156,name="inspect",ref=r~=0 and r or nil},B) end;return B.json.encode(out)',encoding='utf-8')
