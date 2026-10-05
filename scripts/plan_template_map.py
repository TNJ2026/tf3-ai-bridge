"""Offline full-map collection siting from explicit current snapshot and templates."""
import argparse,json,math,time,collections,sys,copy,heapq
from functools import lru_cache
from pathlib import Path
from fullmap_workflow import write_json
from tf3_mcp.site_planner import BoxIndex,transformed,touches,curve
from tf3_mcp.route_planner import Terrain
from tf3_mcp.planning_geometry import facility_aabb
from planning_pipeline_core import load_templates,layout_key,strip_native_evidence,FACILITY_HALF_SIZES,facility_bounds,positioned_bounds
from planning_shared_hubs import select_shared_hubs,POLICY_VERSION
from tf3_mcp.flat_areas import FlatTerrain,preference_key,grid_digest,RESERVE_MARGIN_M,POLICY_VERSION as TERRAIN_POLICY
from tf3_mcp.flat_areas import city_preference_key

def shift_box(box,origin):
 return {side:{a:box[side][a]+origin[a]for a in ('x','y')}for side in ('min','max')}


@lru_cache(maxsize=32)
def _compiled_footprints(key):
 """Geometry only: no map entities, terrain, native approvals or mutable modules."""
 t=json.loads(key);end=min(t['points'],key=lambda p:p['x']);result=[]
 for rot in range(0,360,45):
  a=math.radians(rot);co,si=math.cos(a),math.sin(a)
  def turn(p):return dict(x=co*p['x']-si*p['y'],y=si*p['x']+co*p['y'])
  fac=[]
  for f in t['facilities']:
   p=turn(f['position']);r=rot+f['rotation']
   fac.append(dict(position=p,rotation=r,box=transformed(f['bounds'],p['x'],p['y'],r),
                   reserve=transformed(f['reserve'],p['x'],p['y'],r)))
  points=[turn(p)for p in t['points']+t['links']]
  reserve={side:{a:fn([f['reserve'][side][a]for f in fac]+[p[a]for p in points])+pad
           for a in ('x','y')}for side,fn,pad in [('min',min,-RESERVE_MARGIN_M),('max',max,RESERVE_MARGIN_M)]}
  result.append(dict(rotation=rot,co=co,si=si,end=turn(end),fac=fac,reserve=reserve))
 return result


def compiled_footprints(template,sizes):
 geometry=dict(facilities=[dict(position=f['localPosition'],rotation=f['relativeRotation'],
       bounds=facility_bounds(f,sizes),reserve=facility_bounds(f,sizes,reserved=True))for f in template['facilities']],
       points=[r[k]for r in template['roads']for k in ('position0','position1')],
       links=[r[k]for r in template.get('planningLinks',[])for k in ('position0','position1')])
 return _compiled_footprints(json.dumps(geometry,sort_keys=True,allow_nan=False))


def materialize_candidate(candidate,template,compiled):
 out=dict(candidate);o=out['origin'];fac=[];boxes=[];reserves=[]
 for f,c in zip(template['facilities'],compiled['fac']):
  p={a:o[a]+c['position'][a]for a in ('x','y')};box=shift_box(c['box'],o)
  fac.append((f,p,c['rotation'],box));boxes.append(box);reserves.append(shift_box(c['reserve'],o))
 out.update(fac=fac,boxes=boxes,reserveBoxes=reserves)
 return out


def collection_candidates(template,ordered,nodes,kind,flat_terrain,sizes,target,materialize=True,search_radius=None,city_network_distances=None):
 """Bounded terrain ranking before obstacle checks; includes frontage and reserve space."""
 compiled=compiled_footprints(template,sizes)
 candidates=[]
 for n in ordered[:600]:
  distance=math.dist((nodes[n]['x'],nodes[n]['y']),(target['x'],target['y']))
  if distance>(search_radius if search_radius is not None else (2300 if kind=='city'else 1700)):break
  if kind=='city'and distance<500:continue
  for geometry in compiled:
   rot=geometry['rotation'];co,si=geometry['co'],geometry['si'];v=geometry['end']
   for extension in ((90,170,270)if kind=='city'else(90,170,270,450,650,850)):
    entry=dict(x=nodes[n]['x']+co*extension,y=nodes[n]['y']+si*extension)
    origin=dict(x=entry['x']-v['x'],y=entry['y']-v['y'])
    reserve=shift_box(geometry['reserve'],origin)
    access=dict(min={a:min(nodes[n][a],entry[a])-5 for a in ('x','y')},max={a:max(nodes[n][a],entry[a])+5 for a in ('x','y')})
    profile=flat_terrain.profile(reserve);ap=flat_terrain.profile(access)
    # Unknown/wet collection footprints cannot become terrain-ranked candidates.
    if profile['outsideSurvey']or not profile['dry']:continue
    flat_key=preference_key(profile,ap,distance+extension)
    service_distance=(city_network_distances.get(n,math.inf) if city_network_distances is not None else distance)+extension
    if not math.isfinite(service_distance):continue
    key=city_preference_key(profile,ap,service_distance) if kind=='city' else flat_key
    c=dict(node=n,origin=origin,rotation=rot,entry=entry,
        terrain=profile,accessTerrain=ap,terrainReserve=reserve,flatPreferred=not flat_key[0],rank=key,
        serviceDistanceEstimateM=service_distance)
    candidates.append(materialize_candidate(c,template,geometry)if materialize else c)
 return sorted(candidates,key=lambda c:c['rank'])

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--snapshot',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--baseline',type=Path);ap.add_argument('--redesign',nargs='*',type=int,default=[])
 for name in ('city-template','production-template'):ap.add_argument('--'+name,type=Path,required=True)
 a=ap.parse_args();start=time.time()
 s=json.loads(a.snapshot.read_text('utf8'));d=json.loads((a.output/'details.json').read_text('utf8'));terrain=Terrain(s['grid']);flat_terrain=FlatTerrain(s['grid']);idx=BoxIndex(s['obstacles']);rows=[];roads=[];hubs=[];reserved=[];fail=[]
 flat_path=a.output/'flat_areas.json'
 if flat_path.exists():
  flat_report=json.loads(flat_path.read_text('utf8'))
  assert flat_report['gridDigest']==grid_digest(s['grid'])and flat_report['policy']==TERRAIN_POLICY,'Flat-ground layer changed/stale; regenerate from this snapshot'
 else:
  from plan_flat_areas import run as prepare_flat_areas
  flat_report=prepare_flat_areas(a.snapshot,a.output)
 templates=load_templates(a.city_template,a.production_template)
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
 sizes=FACILITY_HALF_SIZES
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
  reserved=[facility_aabb(f)for f in rows]
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
  search_radius=s.get('planning_policy',{}).get('owner_search_radius_m',{}).get(str(owner))
  if search_radius is not None and (not math.isfinite(search_radius) or search_radius<=0):raise ValueError('Invalid owner search radius')
  city_distances=None
  if kind=='city':
   source=min(nodes,key=lambda n:dist(nodes[n],target));city_distances={source:dist(nodes[source],target)};queue=[(city_distances[source],source)]
   graph=collections.defaultdict(list)
   for edge in edges:
    points=[curve(edge,k/8)for k in range(9)];length=sum(math.dist(x,y)for x,y in zip(points,points[1:]))
    graph[edge['node0']].append((edge['node1'],length));graph[edge['node1']].append((edge['node0'],length))
   while queue:
    length,n=heapq.heappop(queue)
    if length!=city_distances[n]:continue
    for neighbor,cost in graph[n]:
     if length+cost<city_distances.get(neighbor,math.inf):city_distances[neighbor]=length+cost;heapq.heappush(queue,(length+cost,neighbor))
  candidates=collection_candidates(template,ordered,nodes,kind,flat_terrain,sizes,target,materialize=False,search_radius=search_radius,city_network_distances=city_distances);checked=0
  geometry={c['rotation']:c for c in compiled_footprints(template,sizes)}
  for candidate in candidates:
   candidate=materialize_candidate(candidate,template,geometry[candidate['rotation']])
   checked+=1;n=candidate['node'];origin=candidate['origin'];rot=candidate['rotation'];entry=candidate['entry'];angle=math.radians(rot)
   boxes=candidate['boxes'];fac=candidate['fac'];boundary=1e9;valid=True
   for (f,p,rotation,b),reserve_box in zip(fac,candidate['reserveBoxes']):
    if not clear(reserve_box):valid=False;break
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
   rr=dict(id=fid,kind=f['role'],owner=prefix,resource=f['resource'],position=dict(p,z=z),rotation=rotation,params=copy.deepcopy(f['params']),args={},footprint=positioned_bounds(f,p,sizes),reserved=positioned_bounds(f,p,sizes,reserved=True),geometry_basis='estimated local bounds; native preview required',upgrade_policy='directional estimated reserve; actual upgrade modules require native verification' if f.get('upgradeReserveM') else 'no explicit upgrade reserve; enlargement requires renewed site design',command='native_construction',status='candidate')
   rr['upgrade_reserve_m']=copy.deepcopy(f.get('upgradeReserveM',{}))
   rr['params']['year']=s['state']['date']['year']
   rows.append(rr)
  reserved.extend(chosen_terrain['reserveBoxes'])
  rid=prefix+'_external';roads.append(dict(id=rid,from_node_hint=n,from_position=nodes[n],path=[nodes[n],entry],to_facility=fm['truck'],depends_on=list(fm.values()),street_type='country/country_new_medium',port_selector='resolve template frontage endpoint at planned XY',planned_endpoint=entry))
  for j,r in enumerate(template['roads']):
   role=('heliport' if 'heliport' in fm and j==0 else 'truck')
   roads.append(dict(id=prefix+'_internal_'+str(j),path=[transform(r['position0'],origin,angle),transform(r['position1'],origin,angle)],to_facility=fm[role],depends_on=list(fm.values()),street_type=r['roadTemplate'],templateRoad=copy.deepcopy(r),origin=origin,rotation=rot))
  for r in template.get('planningLinks',[]):
   roads.append(dict(id=prefix+'_depot_link',from_facility=fm[r['role']],to_facility=fm[r['targetRole']],path=[transform(r['position0'],origin,angle),transform(r['position1'],origin,angle)],depends_on=list(fm.values()),street_type='country/country_new_small',port_selector=r['basis']))
  h=dict(owner=prefix,entity=owner,kind=kind,position=origin,rotation=rot,node=n,facilities=fm,roads=[r['id']for r in roads if r['id'].startswith(prefix+'_')],template=kind,city_boundary_distance_m=boundary if kind=='city'else None,sharedStockCheck=list(fm.values()),native_verified=False)
  h['terrain_screen']=dict(policy=TERRAIN_POLICY,flatPreferred=chosen_terrain['flatPreferred'],
      serviceDistanceEstimateM=chosen_terrain['serviceDistanceEstimateM'],rankingBasis='city road service distance plus bounded terrain penalty'if kind=='city'else'terrain first',
      footprintAndUpgrade=chosen_terrain['terrain'],externalAccess=chosen_terrain['accessTerrain'],
      reserveBounds=chosen_terrain['terrainReserve'],estimatedUpgradeMarginM=RESERVE_MARGIN_M,
      candidatesRanked=len(candidates),candidatesChecked=checked,sampleSpacingM=s['grid']['spacing'],
      geometryExpanded=checked,geometryPolicy='fixed-footprint-lazy-v1',
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
 if s.get('planning_policy',{}).get('focus_town') is not None:
  focus=next(t for t in s['map']['towns']if t['id']==s['planning_policy']['focus_town'])
 plan=dict(schema=1,layout_input_key=reuse_key,mode='plan_only',build_authorized=False,focus_town=focus['id'],snapshot=str(a.snapshot.resolve()),session=s['state'],cities=s['map']['towns'],industries=s['map']['industries'],facilities=rows,roads=roads,hubs=hubs,ports=[],city_stops=[],line_specs=[],unresolved=fail,templates=templates)
 plan.update(shared_industry_hubs=shared,sharing_policy=POLICY_VERSION,terrain_policy=TERRAIN_POLICY,flat_areas_summary=flat_report['summary'],flat_areas_file='flat_areas.json')
 write_json(a.output/'layout_draft.json',plan);write_json(a.output/'layout_timing.json',{'seconds':time.time()-start,'phase':'offline_template_siting','facilities':len(rows),'failed':len(fail),'geometryCache':_compiled_footprints.cache_info()._asdict(),'geometryExpanded':sum(h.get('terrain_screen',{}).get('geometryExpanded',0)for h in hubs)})
 print(json.dumps({'facilities':len(rows),'hubs':len(hubs),'failed':fail,'seconds':time.time()-start}))
if __name__=='__main__':main()
