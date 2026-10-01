import json
from pathlib import Path
load=lambda f:json.loads(Path(f).read_text(encoding='utf-8'))
stable=load('stable_stop_comparison.json');old=load('bus_purchase_inventory.json');cap=load('stable_capacity_audit.json');bad=load('person_capacity_audit.json')
print('roads',[(r['id'],r['node0'],r['node1'],r['networkNodes']) for r in stable['roads']])
print('depots',json.dumps({'stable':stable['depots'],'before':old['depots']},ensure_ascii=True))
report={'scope':'Live read-only snapshots; stable game kept running at speedup=4. Prior failure snapshots were paused. Counts vary with simulation time.','stableState':stable['game'],'stableAudit':cap,'failureAudit':bad,'stableStopRoads':[{k:r[k] for k in ('id','node0','node1','objects','networkNodes','networkEdges')} for r in stable['roads']],'oldDepot':old['depots'],'stableDepot':stable['depots'],'stableOwnedStations':stable['stations'],'oldOwnedStations':load('bus_line_inventory.json')['stations'],'failureReplacementRoads':[75140,62321,61160,62140,75984,62232],'conclusion':'Stop-associated road replacement and terminal graph changes remain suspects; depot and simulation-age differences prevent attributing causality to stops alone.'}
Path('stable_vs_failure_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
