import json
from pathlib import Path
s=Path('scripts/stop_dual_topology_preview.lua').read_text(encoding='utf-8-sig')
encoded=s[len('local f=assert(load('):];base,idx=json.JSONDecoder().raw_decode(encoded)
pos=base.index(' return B.json.encode(')
base=base[:pos]+''' assert(not pd.errorState.critical and #pd.collisionInfo.collisionEntities==0 and #tn.nodes==4,'preview mismatch')
 local out={built=false,oldEdge=id}
 api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(r,ok)out.built=ok end)
 return B.json.encode(out)
end
'''
Path('scripts/stop_verified_apply.lua').write_text('local f=assert(load('+json.dumps(base)+',"=stopverified","t",_ENV))();return f({edge=61156,name="西北住宅站"},B)',encoding='utf-8')
