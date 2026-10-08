import json, math
from pathlib import Path

snapshot_path = 'D:/Develop/game/tf3/exports/plan_20261004/snapshot-0365e4257d3f.json'
with open(snapshot_path, 'r', encoding='utf-8') as f:
    snap = json.load(f)

towns = snap['map']['towns']
obstacles = snap['obstacles']

buildings_by_town = {t['id']: [] for t in towns}
for o in obstacles:
    if o.get('kind') == 'TOWN_BUILDING':
        tid = o.get('town')
        if tid in buildings_by_town:
            buildings_by_town[tid].append(o)

print('Town building boundaries:')
results = {}
for t in towns:
    bs = buildings_by_town[t['id']]
    tx, ty = t['position']['x'], t['position']['y']
    if bs:
        max_dist = max(math.dist((tx, ty), ((b['min']['x']+b['max']['x'])/2, (b['min']['y']+b['max']['y'])/2)) for b in bs)
        min_x = min(b['min']['x'] for b in bs)
        max_x = max(b['max']['x'] for b in bs)
        min_y = min(b['min']['y'] for b in bs)
        max_y = max(b['max']['y'] for b in bs)
        results[t['id']] = {
            'name': t['name'],
            'center': (tx, ty),
            'radius': max_dist,
            'bbox': ((min_x, min_y), (max_x, max_y)),
            'count': len(bs)
        }
        print(f"{t['name']} (ID {t['id']}): count={len(bs)}, center=({tx}, {ty}), radius={max_dist:.1f}m, bbox=[({min_x:.0f}, {min_y:.0f}) to ({max_x:.0f}, {max_y:.0f})]")
    else:
        results[t['id']] = {'name': t['name'], 'center': (tx, ty), 'radius': 0, 'count': 0}
        print(f"{t['name']} (ID {t['id']}): 0 buildings, center=({tx}, {ty})")
