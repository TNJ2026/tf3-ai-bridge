"""Assemble current-map delivery files and explicit construction/acceptance gates."""
import argparse,json,math,collections,heapq,datetime,csv,io
from pathlib import Path
from fullmap_workflow import write_json,atomic_write
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();R=a.output
p=json.loads((R/'network_plan.json').read_text('utf8'));s=json.loads(Path(p['snapshot']).read_text('utf8'));d=json.loads((R/'details.json').read_text('utf8'))
native={x['id']:x['result']for x in json.loads((R/'native_verified_facilities.json').read_text('utf8'))['results']};groups={x['id']:x['result']for x in json.loads((R/'native_final_groups_v2.json').read_text('utf8'))['results']}
fm={f['id']:f for f in p['facilities']+p['ports']};hm={h['owner']:h for h in p['hubs']};town={t['id']:t for t in p['cities']};industry={i['id']:i for i in p['industries']};stops={x['id']:x for x in p['city_stops']}
def dist(a,b):return math.hypot(a['x']-b['x'],a['y']-b['y'])
for f in fm.values():f['native_preview']=native[f['id']];f['status']='native_single_placement_preview_passed';f['geometry_basis']='Estimated collision screen; native single/group proposal is the placement evidence, bounds are not exact collision polygons'
for road in p['roads']:
 fid=road.get('to_facility');pr=native.get(fid,{}).get('preview',{});f=fm.get(fid)
 if road['id']in ['P14887_truck_access','P34554_truck_access']and pr.get('expectedEntrance'):road['path'][-1]=pr['expectedEntrance']
 if road['id']=='HQ_access':
  ang=math.radians(f['rotation']);road['path'][-1]={'x':f['position']['x']+math.sin(ang)*24,'y':f['position']['y']-math.cos(ang)*24};road['endpoint_basis']='24m local entrance estimate; resolve real port before commit'
 road['execution_gate']='resolve current external, non-frozen ports and endpoint XY; reconnect at actual nodes; preserve turns; new preview before single commit; CAR/TRUCK paths both ways'
 road['geometry_validation']='native standalone road preview; proposed buildings/other roads were absent, so this is not a connected joint preview'
for h in p['hubs']:
 h['native_building_group_preview']=groups[h['owner']];h['native_joint_road_preview']=False;h['construction_method']='staged facilities -> generated external port resolution -> deduplicated template frontage nodes -> depot link -> external road'
 h['inventory_gate']='both aviation stands and truck station must catch the SAME warehouse stocks for every cargo; inspect all warehouse modules'
 h['upgrade_policy']='Captured expanded modules included. Further enlargement only into surveyed free land after a new preview; no guaranteed extra module capacity.'

# Balance total hub traffic across both stands, including several individually small lines.
airlines=[l for l in p['line_specs']if l['mode']=='HELICOPTER'];loads=collections.defaultdict(lambda:[0,0]);totals=collections.Counter()
for l in airlines:
 for end in ['source','destination']:
  if isinstance(l[end],str):totals[fm[l[end]].get('owner')]+=sum(l['cargos'].values())
for l in sorted(airlines,key=lambda l:-sum(l['cargos'].values())):
 for end in ['source','destination']:
  fid=l[end]
  if not isinstance(fid,str):continue
  owner=fm[fid].get('owner');h=hm.get(owner)
  if not h:continue
  lane=min(range(2),key=lambda k:loads[owner][k])if totals[owner]>=60 else 0;loads[owner][lane]+=sum(l['cargos'].values())
  if h['kind']=='production':l[end]=h['facilities']['helipad2'if lane else'helipad'];l[end+'_terminal_index']=0
  else:l[end+'_terminal_index']=lane
  l[end+'_planned_platform']=lane+1
p['aviation_distribution']={k:{'annual_by_platform':v,'trigger':'hub total >=60 cargo/year is planning threshold; tune by actual queue/cycle, not an engine rule'}for k,v in loads.items()}

# Existing road graph gives explicit corridor hints for each feeder and delivery tour.
adj=collections.defaultdict(list);nodes={}
for e in s['obstacles']:
 if e['kind']=='BASE_EDGE':
  n,m=e['node0'],e['node1'];nodes[n]=e['position0'];nodes[m]=e['position1'];w=dist(nodes[n],nodes[m]);adj[n].append((m,w,e['entity']));adj[m].append((n,w,e['entity']))
cache={}
def shortest(a,b):
 if a not in cache:
  ds={a:0};prev={};q=[(0,a)]
  while q:
   w,n=heapq.heappop(q)
   if w!=ds[n]:continue
   for m,c,e in adj[n]:
    if w+c<ds.get(m,1e99):ds[m]=w+c;prev[m]=(n,e);heapq.heappush(q,(w+c,m))
  cache[a]=ds,prev
 ds,prev=cache[a]
 if b not in ds:return None,[]
 ids=[];n=b
 while n!=a:n,e0=prev[n];ids.append(e0)
 return ds[b],ids[::-1]
def loc(v):return fm[v]['position']if isinstance(v,str)else industry[v['existing_industry']]['position']if'existing_industry'in v else town[v['town']]['position']
def node(v):
 if isinstance(v,str):
  h=hm.get(fm[v].get('owner'));anchor=h['node']if h else fm[v].get('road_anchor')
  if anchor is not None:return anchor
 q=loc(v);return min(nodes,key=lambda n:dist(nodes[n],q))
for l in p['line_specs']:
 l['path']=[loc(l['source']),loc(l['destination'])];l['acceptance_required']=['current cargo/model compatibility','explicit source load and destination unload','round trip including queues','cargo delivered to final town/factory stock','deadline headroom','maintenance coverage and capacity']
 if l['mode']=='TRUCK':
  start=node(l['source']);end=node(l['destination']);length,edges=shortest(start,end);l['road_edge_hints']=edges;l['existing_graph_connected']=length is not None;l['road_length_forecast']=length
  if isinstance(l['destination'],dict)and'town'in l['destination']:
   pending=l['destination']['unload_stops'][:];ordered=[];here=loc(l['source'])
   while pending:
    sid=min(pending,key=lambda k:dist(here,stops[k]['position']));pending.remove(sid);ordered.append(sid);here=stops[sid]['position']
   l['destination']['unload_stops']=ordered;l['route_stops']=[l['source']]+ordered+[l['source']]
  else:l['route_stops']=[l['source'],l['destination'],l['source']]
 l['authorization']='planning_only; no vehicles bought'

# Snapshot boundary-to-native-bounds screening. Do not call 500m a noise guarantee.
bt={b['id']:b['town']for b in d['buildings']};tb=collections.defaultdict(list)
for o in s['obstacles']:
 if o['kind']=='TOWN_BUILDING'and o['entity']in bt:tb[bt[o['entity']]].append(o)
def gap(a,b):return math.hypot(*[max(0,a['min'][k]-b['max'][k],b['min'][k]-a['max'][k])for k in ['x','y']])
for h in p['hubs']:
 if h['kind']=='city':h['city_boundary_distance_m']=min(gap(a,b)for fid in h['facilities'].values()for a in native[fid]['bounds']for b in tb[h['entity']]);assert h['city_boundary_distance_m']>=500
assert all(l.get('existing_graph_connected',True)for l in p['line_specs'])
p['validation'].update(facility_single_native_passed=len(native),building_group_native_passed=sum(x['previewPassed']for x in groups.values()),connected_joint_preview_passed=False,construction_authorized=False,static_and_operational_acceptance_required=True)
p['capacity_policy']='Current measured annual output is the baseline. Missing volume stays unmet; exploration, growth or booster benefits are not invented.'
p['execution_gates']=['session/map fingerprint and current entities','native group + connected roads after port resolution','inventory coverage for each cargo','current stopping/terminal indexes','bidirectional paths','explicit cargo config','small fleet measured cycles','same rolling save slot with stable changed file signature']
write_json(R/'network_plan.json',p)

# Fully represented dependency graph. Creation of lines follows all endpoint infrastructure.
jobs=[];facility_ids=set(fm)
for f in fm.values():jobs.append(dict(f,stage='facility',depends_on=[],authorization='not_granted'))
for stage,rows in [('road',p['roads']),('street_stop',p['city_stops']),('line',p['line_specs'])]:
 for row in rows:
  deps=set(row.get('depends_on',[]))
  if stage=='line':
   for end in ['source','destination']:
    v=row[end]
    if isinstance(v,str)and v in fm:
     deps.add(v);h=hm.get(fm[v].get('owner'))
     if h:deps.update(h['roads']);deps.update(h['facilities'].values())
     deps.update(r['id']for r in p['roads']if v in[r.get('from_facility'),r.get('to_facility')])
    elif isinstance(v,dict):deps.update(v.get('unload_stops',[]))
   if row.get('warehouse')in facility_ids:deps.add(row['warehouse'])
  jobs.append(dict(id=row['id'],stage=stage,spec=row,depends_on=sorted(deps),authorization='not_granted'))
write_json(R/'execution_manifest.json',dict(schema=2,session={'player':s['state']['player'],'towns':s['map']['towns'],'industries':s['map']['industries']},jobs=jobs,commit_enabled=False,construction_authorized=False,execution_gates=p['execution_gates']))
changed=[r for r in p['roads']if r['id']in ['HQ_access','P14887_truck_access','P34554_truck_access']]
write_json(R/'entrance_road_recheck.json',dict(p,roads=changed))
print(json.dumps({'facilities':len(fm),'roads':len(p['roads']),'lines':len(p['line_specs']),'graph_connected':True,'city_setback_min':min(h['city_boundary_distance_m']for h in p['hubs']if h['kind']=='city')}))
