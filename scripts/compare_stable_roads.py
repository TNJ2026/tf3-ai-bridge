import json
from pathlib import Path
old=json.loads(Path('mudanjiang_bus_survey.json').read_text(encoding='utf-8'));new=json.loads(Path('stable_bus_survey.json').read_text(encoding='utf-8'))
def roads(d):return {tuple(sorted((x['node0'],x['node1']))):x for x in d['roads']}
a,b=roads(old),roads(new)
changed=[]
for k in a.keys()&b.keys():
 dif={f:[a[k].get(f),b[k].get(f)] for f in ['id','template','p0','p1','t0','t1'] if a[k].get(f)!=b[k].get(f)}
 if dif:changed.append({'endpoints':k,'changes':dif})
print(json.dumps({'oldCounts':{k:len(old[k]) for k in ['roads','buildings']},'newCounts':{k:len(new[k]) for k in ['roads','buildings']},'roadChanged':changed,'roadsOnlyOld':[a[k] for k in a.keys()-b.keys()],'roadsOnlyNew':[b[k] for k in b.keys()-a.keys()]},ensure_ascii=True)[:13000])
