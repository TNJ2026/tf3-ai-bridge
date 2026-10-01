import json
from pathlib import Path
plan=json.loads(Path('line_retest_plan.json').read_text(encoding='utf-8'))
s=Path('scripts/bus_line_create.lua').read_text(encoding='utf-8');s=s[s.index('\n')+1:]
s='local plan=B.json.decode('+json.dumps(json.dumps(plan))+');\nassert(#api.engine.system.lineSystem.getLines()==0,"line already exists; do not duplicate");\n'+s
Path('scripts/line_retest_create.lua').write_text(s,encoding='utf-8')
