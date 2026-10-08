from pathlib import Path
import sys
prefix=sys.argv[1] if len(sys.argv)>1 else 'harbor_turns'
p=Path('scripts/'+prefix+'_apply.lua')
s=Path('scripts/'+prefix+'_preview.lua').read_text(encoding='utf8').replace('return B.json.encode(out)',"assert(not out.critical and #out.messages==0 and out.collisions==0,'repair preview rejected');api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(_,ok)out.applied=ok end);return B.json.encode(out)")
t=p.with_suffix('.tmp');t.write_text(s,encoding='utf8');t.replace(p)
