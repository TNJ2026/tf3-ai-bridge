"""Offline full-map collection siting from explicit current snapshot and templates."""
import argparse,json,math,time,collections,sys,copy
from pathlib import Path
from fullmap_workflow import write_json
from tf3_mcp.site_planner import BoxIndex,transformed,touches,curve
from tf3_mcp.route_planner import Terrain
from planning_pipeline_core import prepare_template,layout_key,strip_native_evidence
from planning_shared_hubs import select_shared_hubs,POLICY_VERSION
from tf3_mcp.flat_areas import FlatTerrain,preference_key,grid_digest,RESERVE_MARGIN_M,POLICY_VERSION as TERRAIN_POLICY

def collection_candidates(template,ordered,nodes,kind,flat_terrain,sizes,target):
 """Bounded terrain ranking before obstacle checks; includes frontage and reserve space."""
 end=min((p for r in template['roads']for p in (r['position0'],r['position1'])),key=lambda p:p['x'])
 candidates=[]
 for n in ordered[:600]:
  distance=math.dist((nodes[n]['x'],nodes[n]['y']),(target['x'],target['y']))
  if distance>(2300 if kind=='city'else 1700):break
  if kind=='city'and distance<500:continue
  for rot in range(0,360,45):
   angle=math.radians(rot);co,si=math.cos(angle),math.sin(angle)
   def transform(p,origin):return dict(x=origin['x']+co*p['x']-si*p['y'],y=origin['y']+si*p['x']+co*p['y'])
   v=transform(end,dict(x=0,y=0))
   for extension in ((90,170,270)if kind=='city'else(90,170,270,450,650,850)):
    entry=dict(x=nodes[n]['x']+co*extension,y=nodes[n]['y']+si*extension)
    origin=dict(x=entry['x']-v['x'],y=entry['y']-v['y']);fac=[];boxes=[]
    for f in template['facilities']:
     p=transform(f['localPosition'],origin);sx,sy=sizes[f['role']];rotation=rot+f['relativeRotation']
     b=transformed(dict(min=dict(x=-sx,y=-sy),max=dict(x=sx,y=sy)),p['x'],p['y'],rotation)
     fac.append((f,p,rotation,b));boxes.append(b)
    points=[transform(r[k],origin)for r in template['roads']+template.get('planningLinks',[])for k in ('position0','position1')]
    reserve=dict(min={a:min([b['min'][a]for b in boxes]+[p[a]for p in points])-RESERVE_MARGIN_M for a in ('x','y')},
                 max={a:max([b['max'][a]for b in boxes]+[p[a]for p in points])+RESERVE_MARGIN_M for a in ('x','y')})
    access=dict(min={a:min(nodes[n][a],entry[a])-5 for a in ('x','y')},max={a:max(nodes[n][a],entry[a])+5 for a in ('x','y')})
    profile=flat_terrain.profile(reserve);ap=flat_terrain.profile(access)
    # Unknown/wet collection footprints cannot become terrain-ranked candidates.
    if profile['outsideSurvey']or not profile['dry']:continue
    key=preference_key(profile,ap,distance+extension)
    candidates.append(dict(node=n,origin=origin,rotation=rot,fac=fac,boxes=boxes,entry=entry,
        terrain=profile,accessTerrain=ap,terrainReserve=reserve,flatPreferred=not key[0],rank=key))
 return sorted(candidates,key=lambda c:c['rank'])

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--snapshot',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--baseline',type=Path);ap.add_argument('--redesign',nargs='*',type=int,default=[]);a=ap.parse_args();start=time.time()
 s=json.loads(a.snapshot.read_text('utf8'));d=json.loads((a.output/'details.json').read_text('utf8'));terrain=Terrain(s['grid']);flat_terrain=FlatTerrain(s['grid']);idx=BoxIndex(s['obstacles']);rows=[];roads=[];hubs=[];reserved=[];fail=[]
 flat_path=a.output/'flat_areas.json'
 if flat_path.exists():
  flat_report=json.loads(flat_path.read_text('utf8'))
  assert flat_report['gridDigest']==grid_digest(s['grid'])and flat_report['policy']==TERRAIN_POLICY,'Flat-ground layer changed/stale; regenerate from this snapshot'
 else:
  from plan_flat_areas import run as prepare_flat_areas
  flat_report=prepare_flat_areas(a.snapshot,a.output)
 root=Path(__file__).resolve().parents[1]
 templates={k:prepare_template(json.loads((root/json.loads((root/f).read_text('utf8'))['template']).read_text('utf8')),k)for k,f in [('city','exports/hub_template_default.json'),('production','exports/hub_template_production_default.json')]}
 reuse_key=layout_key(s,d,templates);frozen=set(d.get('frozenNodes',[]))
 edges=[o for o in s['obstacles']if o['kind']=='BASE_EDGE'];nodes={};degree=collections.Counter()
 for e in edges:
  for n in (0,1):nodes[e['node'+str(n)]]=e['position'+str(n)];degree[e['node'+str(n)]]+=1
 adjacency=collections.defaultdict(set);components={}
 for e in edges:adjacency[e['node0']].add(e['node1']);adjacency[e['node1']].add(e['node0'])
 for n in nodes:
  if n in components:continue
  todo=[n];components[n]=n
  for u in todo:
   for v in adjacency[u]:
    if v not in components:components[v]=n;todo.append(v)
 building_town={b['id']:b['town']for b in d['buildings']};townboxes=collections.defaultdict(list)
 for o in s['obstacles']:
  if o['kind']=='TOWN_BUILDING'and o['entity']in building_town:townboxes[building_town[o['entity']]].append(o)
 sizes={'heliport':(55,60),'warehouse':(48,42),'truck':(45,32),'bus':(28,30),'road_depot':(26,20),'helipad':(18,19),'helipad2':(18,19)}
 def xy(p):return p['x'],p['y']
 def dist(p,q):return math.dist(xy(p),xy(q))
 def pt(x,y):return {'x':x,'y':y}
 def bbox(p,rx,ry):return {'min':pt(p['x']-rx,p['y']-ry),'max':pt(p['x']+rx,p['y']+ry)}
 def gap(b,c):return math.hypot(*[max(0,b['min'][k]-c['max'][k],c['min'][k]-b['max'][k])for k in ('x','y')])
 def transform(p,origin,angle):
  c,n=math.cos(angle),math.sin(angle);return pt(origin['x']+c*p['x']-n*p['y'],origin['y']+n*p['x']+c*p['y'])
 def clear(box):
  if idx.blocked(box)or any(touches(box,r)for r in reserved):return False
  profile=flat_terrain.profile(box)
  return not profile['outsideSurvey']and profile['dry']and profile['heightRangeM']<7
 if a.baseline:
  prior=json.loads(a.baseline.read_text('utf8'));assert prior.get('layout_input_key')==reuse_key,'Baseline geometry/templates/session changed; regenerate layout'
  prior=strip_native_evidence(prior);assert prior['session']['player']==s['state']['player']
  assert [(t['name'],t['position'])for t in prior['cities']]==[(t['name'],t['position'])for t in s['map']['towns']]
  hubs=[h for h in prior['hubs']if h['entity']not in a.redesign];members={v for h in hubs for v in h['facilities'].values()};owners={h['owner']for h in hubs}
  rows=[f for f in prior['facilities']if f['id']in members];roads=[r for r in prior['roads']if r['id'].split('_')[0]in owners]
  reserved=[transformed({'min':pt(f['reserved']['min']['x']-f['position']['x'],f['reserved']['min']['y']-f['position']['y']),'max':pt(f['reserved']['max']['x']-f['position']['x'],f['reserved']['max']['y']-f['position']['y'])},f['position']['x'],f['position']['y'],f['rotation'])for f in rows]
 def corridor(p,q,index=None):
  try:zlast,wet=terrain.sample(p['x'],p['y'])
  except ValueError:return False
  if wet:return False
  for j in range(1,21):
   t=j/20;x=p['x']*(1-t)+q['x']*t;y=p['y']*(1-t)+q['y']*t
   try:z,w=terrain.sample(x,y)
   except ValueError:return False
   if w or (zlast is not None and abs(z-zlast)>dist(p,q)/20*.12):return False
   if j>3 and(index or idx).blocked(bbox(pt(x,y),5,5)):return False
   zlast=z
  return True
 def site(owner,target,kind):
  if any(h['entity']==owner and h['kind']==kind for h in hubs):return
  template=templates[kind];ordered=sorted((n for n in nodes if n not in frozen),key=lambda n:dist(nodes[n],target));chosen=None
  ci=idx
  if kind=='production':
   source=min(nodes,key=lambda n:dist(nodes[n],target));ordered=[n for n in ordered if components[n]==components[source]]
   construction=next(i['construction']for i in d['industries']if i['id']==owner)
   ci=BoxIndex([o for o in s['obstacles']if not(o['kind']=='CONSTRUCTION'and o['entity']==construction)])
  # Generate the same bounded alternatives, rank whole-group terrain first,
  # then find the first candidate satisfying ALL existing spatial/access checks.
  candidates=collection_candidates(template,ordered,nodes,kind,flat_terrain,sizes,target);checked=0
  for candidate in candidates:
   checked+=1;n=candidate['node'];origin=candidate['origin'];rot=candidate['rotation'];entry=candidate['entry'];angle=math.radians(rot)
   boxes=candidate['boxes'];fac=candidate['fac'];boundary=1e9;valid=True
   for f,p,rotation,b in fac:
    if not clear(b):valid=False;break
    if kind=='city':
     distance=min((gap(b,c)for c in townboxes[owner]),default=0)
     if distance<520:valid=False;break
     boundary=min(boundary,distance)
   if not valid or not corridor(nodes[n],entry,ci):continue
   if not all(corridor(transform(r['position0'],origin,angle),transform(r['position1'],origin,angle))for r in template['roads']):continue
   if not all(corridor(transform(r['position0'],origin,angle),transform(r['position1'],origin,angle))for r in template.get('planningLinks',[])):continue
   chosen=(n,origin,rot,fac,boxes,entry,boundary);chosen_terrain=candidate;break
  if not chosen:fail.append({'owner':owner,'kind':kind,'reason':'No bounded coarse site; needs local design'});return
  n,origin,rot,fac,boxes,entry,boundary=chosen;prefix=('T'if kind=='city'else'I')+str(owner);fm={};angle=math.radians(rot)
  for f,p,rotation,b in fac:
   z,_=terrain.sample(p['x'],p['y']);fid=prefix+'_'+f['role'];fm[f['role']]=fid
   sx,sy=sizes[f['role']]
   rr=dict(id=fid,kind=f['role'],owner=prefix,resource=f['resource'],position=dict(p,z=z),rotation=rotation,params=copy.deepcopy(f['params']),args={},footprint=bbox(p,sx,sy),reserved=bbox(p,sx,sy),geometry_basis='estimated local bounds; native preview required',upgrade_policy='template modules retained; extra enlargement requires renewed site design',command='native_construction',status='candidate')
   rr['params']['year']=s['state']['date']['year']
   rows.append(rr)
  reserved.extend(boxes)
  rid=prefix+'_external';roads.append(dict(id=rid,from_node_hint=n,from_position=nodes[n],path=[nodes[n],entry],to_facility=fm['truck'],depends_on=list(fm.values()),street_type='country/country_new_medium',port_selector='resolve template frontage endpoint at planned XY',planned_endpoint=entry))
  for j,r in enumerate(template['roads']):
   role=('heliport' if kind=='city' and j==0 else 'truck')
   roads.append(dict(id=prefix+'_internal_'+str(j),path=[transform(r['position0'],origin,angle),transform(r['position1'],origin,angle)],to_facility=fm[role],depends_on=list(fm.values()),street_type=r['roadTemplate'],templateRoad=copy.deepcopy(r),origin=origin,rotation=rot))
  for r in template.get('planningLinks',[]):
   roads.append(dict(id=prefix+'_depot_link',from_facility=fm[r['role']],to_facility=fm[r['targetRole']],path=[transform(r['position0'],origin,angle),transform(r['position1'],origin,angle)],depends_on=list(fm.values()),street_type='country/country_new_small',port_selector=r['basis']))
  h=dict(owner=prefix,entity=owner,kind=kind,position=origin,rotation=rot,node=n,facilities=fm,roads=[r['id']for r in roads if r['id'].startswith(prefix+'_')],template=kind,city_boundary_distance_m=boundary if kind=='city'else None,sharedStockCheck=list(fm.values()),native_verified=False)
  h['terrain_screen']=dict(policy=TERRAIN_POLICY,flatPreferred=chosen_terrain['flatPreferred'],
      footprintAndUpgrade=chosen_terrain['terrain'],externalAccess=chosen_terrain['accessTerrain'],
      reserveBounds=chosen_terrain['terrainReserve'],estimatedUpgradeMarginM=RESERVE_MARGIN_M,
      candidatesRanked=len(candidates),candidatesChecked=checked,sampleSpacingM=s['grid']['spacing'],
      needsLocalSurvey=s['grid']['spacing']>25,
      fallbackReason=None if chosen_terrain['flatPreferred']else 'No preferred flat candidate passed all bounded layout/access checks; gentler alternative still needs local survey/native preview')
  hubs.append(h);print(json.dumps({'site':prefix,'position':origin,'city_gap':h['city_boundary_distance_m']}),flush=True)
 for t in s['map']['towns']:site(t['id'],t['position'],'city')
 shared=select_shared_hubs(s,hubs)
 for i in s['map']['industries']:
  if any(k in i['fileName']for k in ('oil_platform','fishing_grounds')):continue
  if str(i['id'])in shared:continue
  site(i['id'],i['position'],'production')
 focus=min(s['map']['towns'],key=lambda t:dist(t['position'],pt((s['bounds']['min']['x']+s['bounds']['max']['x'])/2,(s['bounds']['min']['y']+s['bounds']['max']['y'])/2)))
 plan=dict(schema=1,layout_input_key=reuse_key,mode='plan_only',build_authorized=False,focus_town=focus['id'],snapshot=str(a.snapshot.resolve()),session=s['state'],cities=s['map']['towns'],industries=s['map']['industries'],facilities=rows,roads=roads,hubs=hubs,ports=[],city_stops=[],line_specs=[],unresolved=fail,templates=templates)
 plan.update(shared_industry_hubs=shared,sharing_policy=POLICY_VERSION,terrain_policy=TERRAIN_POLICY,flat_areas_summary=flat_report['summary'],flat_areas_file='flat_areas.json')
 write_json(a.output/'layout_draft.json',plan);write_json(a.output/'layout_timing.json',{'seconds':time.time()-start,'phase':'offline_template_siting','facilities':len(rows),'failed':len(fail)})
 print(json.dumps({'facilities':len(rows),'hubs':len(hubs),'failed':fail,'seconds':time.time()-start}))
if __name__=='__main__':main()
