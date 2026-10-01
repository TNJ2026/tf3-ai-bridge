from pathlib import Path
p=Path('scripts/harbor_truck_turns_preview.lua')
s=Path('scripts/harbor_turns_preview.lua').read_text(encoding='utf8').replace('node=70826;local branch=107265','node=70827;local branch=107444').replace('branchEdge.node0==node and branchEdge.node1==106625','branchEdge.node1==node and branchEdge.node0==86037')
t=p.with_suffix('.tmp');t.write_text(s,encoding='utf8');t.replace(p)
