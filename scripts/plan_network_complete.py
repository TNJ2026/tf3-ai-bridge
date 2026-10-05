"""Pure full-map supply, collection and feeder design. Explicit current inputs only."""
import json,math,heapq,collections,time,argparse,sys
from pathlib import Path
from tf3_mcp.site_planner import BoxIndex,curve
from tf3_mcp.planning_geometry import facility_aabb
from fullmap_workflow import write_json
from planning_flow import transport
from planning_shared_hubs import hub_owner,same_hub,shared_fishing_port,validate_fishing_assignments,finalize_land_quantities,city_siting_reviews
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();R=a.output;started=time.time()
L=json.loads((R/'layout_draft.json').read_text('utf8'));SP=Path(L['snapshot']);S=json.loads(SP.read_text('utf8'));D=json.loads((R/'details.json').read_text('utf8'));K=json.loads((R/'capacity.json').read_text('utf8'));G=S['grid']
T={t['id']:dict(t,demand={}) for t in S['map']['towns']};I={i['id']:dict(i,resource=i['fileName'])for i in S['map']['industries']};C={c['id']:c for c in D['cargos']}
for i in D['industries']:I[i['id']].update(i)
for i in K['industries']:I[i['id']].update(i)
for b in D['buildings']:
 for c,v in (b['demands']or{}).items():T[b['town']]['demand'][c]=T[b['town']]['demand'].get(c,0)+v
def pt(x,y,z=None):return dict(x=round(x,3),y=round(y,3),**({}if z is None else {'z':z}))
def xy(p):return p['x'],p['y']
def dst(a,b):return math.dist(xy(a),xy(b))
def box(p,x,y=None):return {'min':pt(p['x']-x,p['y']-(x if y is None else y)),'max':pt(p['x']+x,p['y']+(x if y is None else y))}
def overlap(a,b):return all(a['min'][k]<b['max'][k]and a['max'][k]>b['min'][k]for k in ['x','y'])
def bdist(a,b):return math.hypot(*[max(0,a['min'][k]-b['max'][k],b['min'][k]-a['max'][k])for k in ['x','y']])
def ground(p):
 x=round((p['x']-G['x'])/G['spacing']);y=round((p['y']-G['y'])/G['spacing'])
 if not(0<=x<G['nx']and 0<=y<G['ny']):return None
 k=y*G['nx']+x;return G['heights'][k],G['water'][k]
E=[e for e in S['obstacles']if e['kind']=='BASE_EDGE'];nodes={};adj=collections.defaultdict(list);emap={e['entity']:e for e in E}
for e in E:
 a,b=e['node0'],e['node1'];nodes[a]=e['position0'];nodes[b]=e['position1'];ps=[curve(e,k/8)for k in range(9)];length=sum(math.dist(x,y)for x,y in zip(ps,ps[1:]));adj[a].append((b,length,e['entity']));adj[b].append((a,length,e['entity']))
def nearest(p):return min(nodes,key=lambda n:dst(p,nodes[n]))
cache={}
def shortest(a,b):
 if a not in cache:
  ds={a:0};prev={};q=[(0,a)]
  while q:
   d,u=heapq.heappop(q)
   if d!=ds[u]:continue
   for v,w,e in adj[u]:
    if d+w<ds.get(v,1e20):ds[v]=d+w;prev[v]=(u,e);heapq.heappush(q,(d+w,v))
  cache[a]=ds,prev
 ds,prev=cache[a]
 if b not in ds:return None,[]
 path=[];v=b
 while v!=a:v0,e=prev[v];path.append(e);v=v0
 return ds[b],path[::-1]
comp={}
for n in nodes:
 if n in comp:continue
 todo=[n];comp[n]=n
 for u in todo:
  for v,_,_ in adj[u]:
   if v not in comp:comp[v]=n;todo.append(v)
pos={**{k:v['position']for k,v in I.items()},**{k:v['position']for k,v in T.items()}}
def cost(a,b):
 rd,_=shortest(nearest(pos[a]),nearest(pos[b]));return min((rd/11+100)if rd is not None else 1e6,dst(pos[a],pos[b])/45+330)
links=[]
def link(a,b,c,v,stage):
 if v>1e-5:links.append(dict(source=a,destination=b,cargo=c,annual=round(v,5),stage=stage))
def caps(c):return {i['id']:i['outputs'][str(c)]for i in I.values()if str(c)in i['outputs']}

# Core-input demands exclude optional tools/machines/fertilizer boosters.
recipes={'livestock_farm':(1,7),'saw_mill':(12,13),'cement_plant':(24,15),'oil_refinery':(18,20),'bricks_works':(23,33)}
processed_cargos={finished for raw,finished in recipes.values()}
city_cargos={int(c) for t in T.values() for c in t['demand']}
available={c:caps(c) for c in sorted(city_cargos-processed_cargos)};raw_summary=[]
for typ,(raw,finished)in recipes.items():
 processors={i['id']:i for i in I.values()if i['resource'].split('/')[-2]==typ}
 sup=caps(raw);needs={k:v['inputs'][str(raw)]for k,v in processors.items()};rawtotal=sum(sup.values());demtotal=sum(needs.values())
 # Keep every processor in the whole-map service plan under input scarcity.
 # Equal utilization is a deliberate service policy; rates remain forecasts.
 utilization=min(1,rawtotal/demtotal) if demtotal else 0
 desired={k:v*utilization for k,v in needs.items()}
 for a,b,v in transport(sup,desired,cost):link(a,b,raw,v,'input')
 available[finished]={k:sum(x['annual']for x in links if x['destination']==k and x['cargo']==raw)*processors[k]['outputs'][str(finished)]/needs[k]for k in needs}
 raw_summary.append(dict(cargo=raw,available=rawtotal,full_processor_input=demtotal,gap=max(0,demtotal-rawtotal),surplus=max(0,rawtotal-demtotal)))
supply=[]
for c,sup in available.items():
 dem={k:t['demand'][str(c)]for k,t in T.items()if str(c)in t['demand']};total=sum(dem.values());avail=sum(sup.values());ratio=min(1,avail/total)if total else 0
 for a,b,v in transport(sup,{k:v*ratio for k,v in dem.items()},cost):link(a,b,c,v,'city_supply')
 if not total and not avail:continue
 supply.append(dict(cargo=c,name=C[c]['name'],demand=total,available=round(avail,3),allocated=round(min(total,avail),3),gap=round(max(0,total-avail),3)))
# Co-product fertilizer may improve farms, but its unmeasured production uplift is not counted.
fs={k:available[20][k]*I[k]['outputs']['3']/I[k]['outputs']['20']for k in available[20]};fd={i['id']:i['inputs']['3']for i in I.values()if '3'in i['inputs']}
for a,b,v in transport(fs,fd,cost):link(a,b,3,v,'optional_booster')
connector_roads=[]
buildings={o['entity']:o for o in S['obstacles']if o['kind']=='TOWN_BUILDING'};townboxes=collections.defaultdict(list)
for b in D['buildings']:
 if b['id']in buildings:townboxes[b['town']].append(buildings[b['id']])
allbuild=list(buildings.values());idx=BoxIndex(S['obstacles']);reserves=[];fac=[];roads=list(connector_roads);hubs={};ports=[]
def clear(b,slope=9):
 if idx.blocked(b)or any(overlap(b,r)for r in reserves):return False
 vals=[]
 for x in [b['min']['x'],(b['min']['x']+b['max']['x'])/2,b['max']['x']]:
  for y in [b['min']['y'],(b['min']['y']+b['max']['y'])/2,b['max']['y']]:
   g=ground(pt(x,y))
   if g is None or g[1]:return False
   vals.append(g[0])
 return max(vals)-min(vals)<=slope
def add(fid,kind,p,rot,cmd,args,r,**extra):
 g=ground(p);f=dict(id=fid,kind=kind,position=pt(p['x'],p['y'],g[0]if g else 2),rotation=rot,command=cmd,args=dict(args,x=p['x'],y=p['y'],z=g[0]if g else 2,rotation=rot,connect=False),footprint=box(p,min(r,54)),reserved=box(p,r),status='candidate_requires_native_preview',**extra);fac.append(f);reserves.append(f['reserved']);return f
def access(f,n,entrance=None):
 a=nodes[n];p=entrance or f['position'];length=dst(a,p);v=pt((p['x']-a['x']),p['y']-a['y'])
 road=dict(id=f['id']+'_access',from_node_hint=n,from_position=a,to_facility=f['id'],path=[a,p],geometry={'type':'straight_or_tangent_hermite','startTangent':v,'endTangent':v},native_verified=False,depends_on=[f['id']],port_selector='resolve actual external BASE_NODE after build; never connect to construction centre',street_type='country/country_new_small',length_m=round(length,2))
 roads.append(road);f['road_anchor']=n;return road

# Preserve all facilities from the selected collection templates.
fac=L['facilities'];roads=L['roads'];hubs={h['owner']:h for h in L['hubs']};reserves=[facility_aabb(f)for f in fac];ports=[]
for h in hubs.values():
 for fid in h['facilities'].values():
  f=next(f for f in fac if f['id']==fid);f['road_anchor']=h['node']
  if f['kind']=='road_depot':f.update(service_radius=400,maintenance_pool=12)
  if f['kind']=='road_maintenance':f.update(service_radius=600,maintenance_pool=16)
watercomponents={};waterparents={}
for k,w in enumerate(G['water']):
 if not w or k in watercomponents:continue
 todo=[k];watercomponents[k]=k
 for u in todo:
  x,y=u%G['nx'],u//G['nx']
  for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
   xx,yy=x+dx,y+dy;v=yy*G['nx']+xx
   if 0<=xx<G['nx']and 0<=yy<G['ny']and G['water'][v]and v not in watercomponents:watercomponents[v]=k;todo.append(v)
def cell(p):return round((p['y']-G['y'])/G['spacing'])*G['nx']+round((p['x']-G['x'])/G['spacing'])
def waterpath(a,b):
 ka,kb=cell(a),cell(b)
 if ka not in watercomponents:ka=min(watercomponents,key=lambda k:dst(pt(G['x']+k%G['nx']*G['spacing'],G['y']+k//G['nx']*G['spacing']),a))
 if kb not in watercomponents:kb=min(watercomponents,key=lambda k:dst(pt(G['x']+k%G['nx']*G['spacing'],G['y']+k//G['nx']*G['spacing']),b))
 todo=collections.deque([ka]);prev={ka:None}
 while todo and kb not in prev:
  u=todo.popleft();x,y=u%G['nx'],u//G['nx']
  for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
   xx,yy=x+dx,y+dy;v=yy*G['nx']+xx
   if 0<=xx<G['nx']and 0<=yy<G['ny']and v in watercomponents and v not in prev:prev[v]=u;todo.append(v)
 if kb not in prev:return []
 path=[];v=kb
 while v is not None:path.append(pt(G['x']+v%G['nx']*G['spacing'],G['y']+v//G['nx']*G['spacing']));v=prev[v]
 return path[::-1]
fish_annual={i['id']:sum(l['annual']for l in links if l['source']==i['id'])for i in I.values()if 'fishing_grounds'in i['resource']}
fish_budget=S.get('planning_policy',{}).get('fish_port_annual_handling_budget')
fish_decisions=[]
for i in sorted(I.values(),key=lambda i:i['id']):
 if 'fishing_grounds'not in i['resource']:continue
 if fish_annual[i['id']]<=0:
  fish_decisions.append(dict(industry=i['id'],decision='no_allocated_flow',native_verified=False));continue
 shared_port=shared_fishing_port(i,ports,I,waterpath,fish_annual[i['id']],fish_budget)
 if shared_port:
  port=shared_port['port'];port['service_industries'].append(i['id']);port['annual_forecast']+=fish_annual[i['id']]
  port['water_routes_by_industry'][str(i['id'])]=dict(outbound=shared_port['outbound'],inbound=shared_port['inbound'],native_verified=False)
  fish_decisions.append(dict(industry=i['id'],port=port['id'],decision='shared_pair',native_verified=False));continue
 options=[];sourcecell=cell(i['position']);component=watercomponents.get(sourcecell)
 print('coast '+str(i['id']),flush=True)
 for k,w in enumerate(G['water']):
  if w:continue
  x,y=k%G['nx'],k//G['nx'];p=pt(G['x']+x*G['spacing'],G['y']+y*G['spacing'])
  if dst(p,i['position'])>3300:continue
  for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
   xx,yy=x+dx,y+dy;wk=yy*G['nx']+xx
   if not(0<=xx<G['nx']and 0<=yy<G['ny'])or wk not in watercomponents or watercomponents[wk]!=component:continue
   n=nearest(p);land=pt(p['x']-dx*100,p['y']-dy*100)
   if not clear(box(land,45)):continue
   pad_positions=[pt(p['x']-dx*120-dy*s,p['y']-dy*120+dx*s)for s in (-50,50)]
   if not all(clear(box(q,25))for q in pad_positions):continue
   options.append((dst(p,i['position']),p,dx,dy,n))
 if not options:raise ValueError('No fish coast '+str(i['id']))
 _,p,dx,dy,n=min(options,key=lambda x:x[0]);rot=math.degrees(math.atan2(dx,-dy))%360;fid='P'+str(i['id']);shore=pt(p['x']+dx*15,p['y']+dy*15)
 # Fine native coastal adjustment is performed separately; store the full alternative set.
 wh=pt(p['x']-dx*80,p['y']-dy*80)
 wf=add(fid+'_warehouse','warehouse',wh,rot,'build_warehouse',{'module_count':1},30,owner=fid,road_required=False)
 pads=[]
 for role,s in [('helipad',-50),('helipad2',50)]:
  q=pt(p['x']-dx*120-dy*s,p['y']-dy*120+dx*s)
  pads.append(add(fid+'_'+role,role,q,rot,'build_helipad',{},25,owner=fid,road_required=False))
 port=dict(id=fid+'_harbor',kind='harbor',industry=i['id'],position=shore,rotation=rot,water_direction=pt(dx,dy),warehouse=wf['id'],helipad=pads[0]['id'],helipad2=pads[1]['id'],transfer_mode='HELICOPTER',node=n,shoreline_revision='native_small_pier_v1',candidates=[{'position':v,'water_direction':pt(a,b),'node':nn}for _,v,a,b,nn in sorted(options,key=lambda x:x[0])[:80]],waterRoute=waterpath(i['position'],shore),status='requires_fine_coast_preview')
 port.update(service_industries=[i['id']],annual_forecast=fish_annual[i['id']],
  water_routes_by_industry={str(i['id']):dict(outbound=port['waterRoute'],inbound=waterpath(shore,i['position']),native_verified=False)},
  capacity_review=dict(annual_handling_budget=fish_budget,verified=False,required=['both field round trips and ship type','shipyard round trip','maintenance area','berths fleet and two helipads throughput','shared warehouse inventory']))
 if not port['waterRoute'] or not port['water_routes_by_industry'][str(i['id'])]['inbound']:raise ValueError('No sampled fishing round trip '+str(i['id']))
 fish_decisions.append(dict(industry=i['id'],port=port['id'],decision='independent_port',native_verified=False))
 ports.append(port);reserves.append(box(shore,45));pos[fid]=wh
# HQ: beside the terminal street segment, never beyond the dead end.
focus=L['focus_town'];target=T[focus]['position'];hq=None
for n in sorted((n for n in nodes if len(adj[n])==1 and dst(nodes[n],target)<950),key=lambda n:dst(nodes[n],target)):
 other,length,eid=adj[n][0];edge=emap[eid]
 if length<1:continue
 for setback in [25,45,65]:
  fraction=min(setback/length,.5);t=fraction if edge['node0']==n else 1-fraction
  q=curve(edge,t);lo=curve(edge,max(0,t-.01));hi=curve(edge,min(1,t+.01))
  tx,ty=hi[0]-lo[0],hi[1]-lo[1];norm=math.hypot(tx,ty)
  if norm<1e-6:continue
  for offset in [60,70,85]:
   for side in [1,-1]:
    away=pt(-ty/norm*side,tx/norm*side)
    p=pt(q[0]+away['x']*offset,q[1]+away['y']*offset)
    rot=math.degrees(math.atan2(-away['x'],away['y']))%360
    if clear(box(p,50)):
     hq=add('HQ','headquarters',p,rot,'build_headquarters',{'town':focus},50,
      town_name=T[focus]['name'],road_anchor=n,
      road_frontage={'edge_hint':eid,'position':pt(q[0],q[1]),'side':side,
       'placement':'beside_terminal_segment','native_verified':False,
       'verification_required':'entrance orientation, frontage gap/height and native pedestrian access'},
      road_basis='fronts existing street; no speculative road to construction centre')
     break
   if hq:break
  if hq:break
 if hq:break
if not hq:raise ValueError('No HQ roadside site near a central road end')

def service_site(fid,kind,target,radius,command,args,first=True):
 for n in sorted(nodes,key=lambda n:dst(nodes[n],target))[:300]:
  for rot in range(0,360,45):
   a=math.radians(rot);p=pt(nodes[n]['x']-math.sin(a)*65,nodes[n]['y']+math.cos(a)*65)
   if clear(box(p,radius)):
    f=add(fid,kind,p,rot,command,args,radius);access(f,n);return f
 raise ValueError('No service site '+fid)
# City stop set cover: every currently demanded building gets a candidate unloading stop.
stops=[];delivery=[]
for tid,t in T.items():
 bs={b['id']:b for b in D['buildings']if b['town']==tid and b['demands']and b['id']in buildings};remaining=set(bs)
 centres={k:pt((buildings[k]['min']['x']+buildings[k]['max']['x'])/2,(buildings[k]['min']['y']+buildings[k]['max']['y'])/2)for k in bs};candidates=[]
 for e in E:
  if min(dst(e['position0'],t['position']),dst(e['position1'],t['position']))>1400:continue
  for param in [.2,.4,.6,.8]:
   p=pt(*curve(e,param));cover={k for k,v in centres.items()if dst(v,p)<=135}
   if cover:candidates.append((e,param,p,cover))
 ids=[]
 while remaining:
  e,param,p,cov=max(candidates,key=lambda q:len(q[3]&remaining));fresh=cov&remaining
  if not fresh:raise ValueError('Uncovered demands '+str(tid))
  remaining-=cov;sid='STOP'+str(tid)+'_%02d'%(len(ids)+1);ids.append(sid)
  stops.append(dict(id=sid,town=tid,position=p,edge_hint=e['entity'],edge_endpoints=[e['position0'],e['position1']],param=param,side='right',kind='mid',two_sided=True,command='build_street_stop',covered_building_hints=sorted(fresh),load=False,unload=True,coverage_status='135m conservative centroid screen; native catchables still required'))
 delivery.append(dict(id='DELIVERY'+str(tid),town=tid,start=hubs['T'+str(tid)]['facilities']['truck']if'T'+str(tid)in hubs else None,stops=ids,cargos=[int(c)for c in t['demand']],return_to_start=True,status='air_last_mile'if'T'+str(tid)in hubs else'direct_road_delivery_in_supply_routes'))
growth=[]
for tid,t in T.items():
 bs=townboxes[tid];b={'min':pt(min(x['min']['x']for x in bs),min(x['min']['y']for x in bs)),'max':pt(max(x['max']['x']for x in bs),max(x['max']['y']for x in bs))}
 growth.append(dict(town=tid,built_bounds=b,near_term_envelope={'min':pt(b['min']['x']-200,b['min']['y']-200),'max':pt(b['max']['x']+200,b['max']['y']+200)},long_term_envelope={'min':pt(b['min']['x']-400,b['min']['y']-400),'max':pt(b['max']['x']+400,b['max']['y']+400)},basis='planning buffers only; expansion likely along connected dry gentle roads, constrained by water/terrain; no growth date/radius guarantee'))

# Quantity and endpoint changes invalidate historical coastal previews.
# Refine this plan's current paired port after network generation.
# One ship maintenance facility per fishing port; never infer purchase capability.
for port in ports:
 p=port['position'];dx,dy=port['water_direction']['x'],port['water_direction']['y']
 servicepos=pt(p['x']-dy*110,p['y']+dx*110)
 f=add(port['id']+'_maintenance','water_maintenance',servicepos,port['rotation'],'native_construction',{},40,owner='P'+str(port['industry']),service_radius=1400,maintenance_pool=12)
 f.update(resource='::/depots/water/water_maint_station.con',road_required=False,status='requires_fine_coast_preview')
 depotpos=pt(p['x']+dy*220,p['y']-dx*220)
 depot=add(port['id']+'_shipyard','water_depot',depotpos,port['rotation'],'native_construction',{},60,owner='P'+str(port['industry']),road_required=False)
 depot.update(resource='::/depots/water/water_depot.con',status='requires_fine_coast_preview')
 port.update(command='native_construction',args={},footprint=box(p,45),reserved=box(p,60),maintenance_base=f['id'],purchase_base=depot['id'],
  collection_template='config/planning_templates/fish_port_air.json',collection_status='experimental_requires_joint_native_preview',cargo_policy={'allowed':['fish'],'oil':'helicopter'},purchase_capability_verified=False)

coast=json.loads((R/'coast_layout.json').read_text('utf8'))if(R/'coast_layout.json').exists()else None
if coast:
 raise ValueError('Legacy coast_layout must be regenerated against current paired-port service assignments')
for port in ports:
 port['capacity_review']['forecast_exceeds_budget']=fish_budget is not None and port['annual_forecast']>fish_budget
fm={f['id']:f for f in fac};pm=validate_fishing_assignments(ports,I);routes=[]
if set(pm)!={i for i,v in fish_annual.items()if v>0}:raise ValueError('Fishing service coverage lost or duplicated')
def air(h,second=False):return h['facilities'].get('helipad2'if second else'helipad',h['facilities'].get('heliport'))
def industry_end(i):return dict(existing_industry=i,resource=I[i]['resource'],position=pos[i],stations_hint=I[i]['stations'])
def consumer(i):return industry_end(i) if i in I else dict(town=i,unload_stops=next(d['stops']for d in delivery if d['town']==i))
for j,l in enumerate(links,1):
 a,b,c=l['source'],l['destination'],l['cargo'];pa,pb=pos[a],pos[b];ha=hubs.get(hub_owner(a,True,L.get('shared_industry_hubs',{})));hb=hubs.get(hub_owner(b,b in I,L.get('shared_industry_hubs',{})));port=pm.get(a);offshore='oil_platform'in I[a]['resource']
 na=port['node']if port else nearest(pa);nb=nearest(pb);rd,rp=shortest(na,nb);rt=rd/11+90 if rd is not None and not offshore else None;at=dst(pa,pb)/45+330
 mode='HELICOPTER'if offshore or rt is None or (dst(pa,pb)>4000 and at<rt*.7)else'TRUCK'
 if c==6 and rt is not None and rt>750:mode='HELICOPTER'
 if same_hub(ha,hb) and rt is not None and not offshore:mode='TRUCK'
 chain=[];src=industry_end(a);dstend=consumer(b)
 if port:
  chain.append(dict(mode='SMALL_SHIP',**{'from':src,'to':port['id']},warehouse=port['warehouse'],purchase_base=port['purchase_base'],maintenance_base=port['maintenance_base'],planned_water_route=port['water_routes_by_industry'][str(a)],service_industries=port['service_industries']))
  src=port['helipad'];mode='HELICOPTER'
 if mode=='HELICOPTER':
  if not hb or (not ha and not port and not offshore):raise ValueError('Required air-transfer collection has no feasible layout for flow '+str(a)+' -> '+str(b))
  if ha and not port:chain.append(dict(mode='TRUCK',**{'from':src,'to':ha['facilities']['truck']},warehouse=ha['facilities']['warehouse']))
  chain.append(dict(mode='HELICOPTER',**{'from':src if port else air(ha)if ha else src,'to':air(hb)},source_second=port['helipad2']if port else air(ha,True)if ha else None,destination_second=air(hb,True),warehouse=hb['facilities']['warehouse'],maintenance_base=next(h['facilities']['heliport']for h in hubs.values()if h['kind']=='city')))
  chain.append(dict(mode='TRUCK',**{'from':hb['facilities']['truck'],'to':dstend}))
 else:chain.append(dict(mode='TRUCK',**{'from':src,'to':dstend}))
 routes.append(dict(id='R%03d'%j,**l,mode=mode,path=[pa,pb],road_edges=rp,transfer_chain=chain,alternatives={'road_seconds':rt,'air_seconds':at,'basis':'11m/s road;45m/s air;330s transfer estimate'},native_path_verified=False))

hubs,fac,roads,quantity_decisions=finalize_land_quantities(hubs,fac,roads,routes,list(T.values()),list(I.values()))
quantity_decisions['unused_layout_issues']=L.get('unresolved',[])
quantity_decisions.update(fishing=fish_decisions,new_fishing_collections=len(ports),
    fish_field_to_port={str(k):v['id']for k,v in pm.items()})
for row in delivery:
 if 'T'+str(row['town'])not in hubs:row.update(start=None,status='direct_road_delivery_in_supply_routes')
fm={f['id']:f for f in fac}
# Aggregate identical directional movements, then split high-throughput aviation.
def key(v):return v if isinstance(v,str)else'I'+str(v['existing_industry'])if'existing_industry'in v else'T'+str(v['town'])
def location(v):return fm[v]['position']if isinstance(v,str)and v in fm else next(p['position']for p in ports if p['id']==v)if isinstance(v,str)else v['position']if'existing_industry'in v else T[v['town']]['position']
movements={}
for r in routes:
 for leg in r['transfer_chain']:
  kk=(leg['mode'],key(leg['from']),key(leg['to']));m=movements.setdefault(kk,dict(leg,cargos={},flows=[]));m['cargos'][str(r['cargo'])]=m['cargos'].get(str(r['cargo']),0)+r['annual'];m['flows'].append(r['id'])
lines=[]
for m in movements.values():
 total=sum(m['cargos'].values());split=m['mode']=='HELICOPTER'and total>=60 and bool(m.get('source_second')or m.get('destination_second'));count=2 if split else 1
 for lane in range(count):
  src=m.get('source_second')if lane and m.get('source_second')else m['from'];dest=m.get('destination_second')if lane and m.get('destination_second')else m['to'];p0,p1=location(src),location(dest)
  cap=12 if m['mode']=='HELICOPTER'else 30 if m['mode']=='SMALL_SHIP'else 22;speed=45 if m['mode']=='HELICOPTER'else 7 if m['mode']=='SMALL_SHIP'else 9
  forecast=dst(p0,p1)/speed+120;cargo={c:v/count for c,v in m['cargos'].items()};cid=[int(c)for c in cargo]
  lines.append(dict(id='LINE%03d'%(len(lines)+1),mode=m['mode'],source=src,destination=dest,cargos=cargo,flows=m['flows'],path=[p0,p1],warehouse=m.get('warehouse'),purchase_base=m.get('purchase_base'),maintenance_base=m.get('maintenance_base'),load_at_source=cid,load_at_destination=[],unload_at_destination=cid,cargo_index_offset=1,return_to_source=True,source_terminal_index=lane if src==m['from']and split else 0,destination_terminal_index=lane if dest==m['to']and split else 0,terminal_gate='resolve current station+terminal; distinct pad entities or distinct landing terminals; block if unsupported',parallel_split=count,capacity_forecast=cap,oneway_seconds_forecast=forecast,fleet_forecast=max(1,math.ceil(total/count*1.25*2*forecast/(1460*cap))),vehicle_model='::/vehicle/helicopter/piasecki_h21/piasecki_h21.mdl'if m['mode']=='HELICOPTER'else'::/vehicle/ship/votrans_universal/votrans_universal.mdl'if m['mode']=='SMALL_SHIP'else'::/vehicle/truck/gmc_660_dfm/gmc_660_dfm_univ.mdl',deadline_seconds=min(C[c]['timeToDeliverInSeconds']for c in cid),forecast_only=True))

# Service endpoints, not every metre of road. New fields remain forecasts until readback.
selected=[f for f in fac if f['kind']in ('road_depot','road_maintenance')];uncovered=[l for l in lines if l['mode']=='TRUCK'and not any(min(dst(location(l['source']),f['position']),dst(location(l['destination']),f['position']))<f.get('service_radius',0)-50 for f in selected)]
while uncovered:
 l=uncovered[0];target=location(l['destination']);f=service_site('MAINT_%02d'%(1+sum(x['kind']=='road_maintenance'for x in fac)),'road_maintenance',target,24,'native_construction',{})
 f.update(service_radius=600,maintenance_pool=16,road_required=False,road_basis='native maintenance area service; no road port')
 roads[:]=[r for r in roads if r.get('to_facility')!=f['id']];selected.append(f)
 remaining=[l for l in uncovered if min(dst(location(l['source']),f['position']),dst(location(l['destination']),f['position']))>=550]
 if len(remaining)==len(uncovered):break
 uncovered=remaining
for l in lines:
 if l['mode']=='TRUCK':l['maintenance_sites']=[f['id']for f in selected if min(dst(location(l['source']),f['position']),dst(location(l['destination']),f['position']))<f.get('service_radius',0)-50]

plan=dict(L,cities=list(T.values()),industries=list(I.values()),supply=supply,raw_supply=raw_summary,facilities=fac,roads=roads,hubs=list(hubs.values()),ports=ports,routes=routes,city_stops=stops,city_delivery=delivery,growth=growth,line_specs=lines,byproducts=[dict(industry=i['id'],cargo=int(c),policy='No current verified demand; no speculative delivery line')for i in I.values()for c in i['outputs']if int(c)not in({1,3,6,7,12,13,15,18,20,24}|city_cargos)],nonselected_modes={'passenger_rail':'No measured passenger OD; collection includes bus facility; passenger line deferred to demand study','cargo_rail':'Current small dispersed annual volumes favor road/air; rail corridor only if sustained bulk demand rises','runway_airport':'11.3km map; helicopter direct paths avoid runway/taxi footprint and transfers'},validation={'native_preview_required':True,'construction_authorized':False,'maintenance_uncovered':[l['id']for l in uncovered]},planning_seconds=time.time()-started)
plan['shared_hub_capacity_review']=[]
plan['unresolved']=[]  # Required endpoint failures stopped routing above.
plan['collection_quantity_decisions']=quantity_decisions
plan['city_siting_reviews']=city_siting_reviews(plan['hubs'],plan['cities'])
plan['shared_fishing_ports']={str(k):dict(port=v['id'],service_industries=v['service_industries'],annual_forecast=v['annual_forecast'],capacity_verified=False,native_path_verified=False)for k,v in pm.items()}
for owner in sorted({v['hub_owner']for v in L.get('shared_industry_hubs',{}).values()}):
 if owner not in hubs:continue
 h=hubs[owner];members=set(h['facilities'].values());traffic=[]
 for line in lines:
  for end in ('source','destination'):
   if isinstance(line[end],str)and line[end]in members:
    traffic.append(dict(line=line['id'],direction=end,mode=line['mode'],cargos=line['cargos']))
 plan['shared_hub_capacity_review'].append(dict(owner=owner,industries=[int(i)for i,v in L['shared_industry_hubs'].items()if v['hub_owner']==owner],traffic=traffic,capacity_verified=False,required_checks=['industry round-trip road path','common warehouse stock','aggregate storage and truck terminal throughput','two landing terminals and fleet capacity'],note='Directional handling forecasts; do not sum both ends as additional supply. Expand or restore separate production hub if capacity fails.'))
fm={f['id']:f for f in fac+ports};known=set(fm)|{r['id']for r in roads}|{st['id']for st in stops}
jobs=[]
for f in fac+ports:
 port=next((p for p in ports if f['id']in {p['id'],p['warehouse'],p['helipad'],p['helipad2'],p['maintenance_base'],p['purchase_base']}),None)
 extra=dict(collection_owner=port['id'],service_industries=port['service_industries'],requiredNativeChecks=port['capacity_review']['required'])if port else{}
 jobs.append(dict({**f,**extra},stage='facility',depends_on=[],authorization='not_granted'))
for stage,rows in [('road',roads),('street_stop',stops),('line',lines)]:
 for row in rows:
  deps=row.get('depends_on',[])if stage!='line'else sorted({v for v in [row['source'],row['destination'],row.get('warehouse'),row.get('purchase_base'),row.get('maintenance_base')]if isinstance(v,str)and v in known}|{r['id']for r in roads if r.get('to_facility')in[row['source'],row['destination']]}|{x for v in[row['source'],row['destination']]if isinstance(v,dict)for x in v.get('unload_stops',[])})
  jobs.append(dict(id=row['id'],stage=stage,spec=row,depends_on=deps,authorization='not_granted'))
manifest=dict(schema=1,session={'player':S['state']['player'],'towns':S['map']['towns'],'industries':S['map']['industries']},jobs=jobs,commit_enabled=False,execution_policy='fresh session+late-bound entity/port -> native preview -> single commit after authorization -> bidirectional paths+catchment+inventory -> save')
write_json(R/'network_plan.json',plan);write_json(R/'execution_manifest.json',manifest)
print(json.dumps({'facilities':len(fac),'ports':len(ports),'roads':len(roads),'lines':len(lines),'stops':len(stops),'supply':supply,'seconds':time.time()-started},ensure_ascii=True))
