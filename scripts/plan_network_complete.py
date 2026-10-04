"""Pure full-map supply, collection and feeder design. Explicit current inputs only."""
import json,math,heapq,collections,time,argparse,sys
from pathlib import Path
from tf3_mcp.site_planner import BoxIndex,curve
from fullmap_workflow import write_json
from planning_flow import transport
from planning_shared_hubs import hub_owner,same_hub
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
recipes={'livestock_farm':(1,7),'saw_mill':(12,13),'cement_plant':(24,15),'oil_refinery':(18,20)}
processed_cargos={finished for raw,finished in recipes.values()}
city_cargos={int(c) for t in T.values() for c in t['demand']}
available={c:caps(c) for c in sorted(city_cargos-processed_cargos)};raw_summary=[]
for typ,(raw,finished)in recipes.items():
 processors={i['id']:i for i in I.values()if i['resource'].split('/')[-2]==typ}
 sup=caps(raw);needs={k:v['inputs'][str(raw)]for k,v in processors.items()};rawtotal=sum(sup.values());demtotal=sum(needs.values())
 # Allocate scarce grain first to the better conversion, then minimize transport.
 desired={k:0 for k in needs};left=rawtotal
 for k in sorted(needs,key=lambda k:(-processors[k]['outputs'][str(finished)]/needs[k],min(cost(a,k)for a in sup))):desired[k]=min(needs[k],left);left-=desired[k]
 for a,b,v in transport(sup,desired,cost):link(a,b,raw,v,'input')
 available[finished]={k:sum(x['annual']for x in links if x['destination']==k and x['cargo']==raw)*processors[k]['outputs'][str(finished)]/needs[k]for k in needs}
 raw_summary.append(dict(cargo=raw,available=rawtotal,full_processor_input=demtotal,gap=max(0,demtotal-rawtotal),surplus=max(0,rawtotal-demtotal)))
supply=[]
for c,sup in available.items():
 dem={k:t['demand'][str(c)]for k,t in T.items()if str(c)in t['demand']};total=sum(dem.values());avail=sum(sup.values());ratio=min(1,avail/total)if total else 0
 for a,b,v in transport(sup,{k:v*ratio for k,v in dem.items()},cost):link(a,b,c,v,'city_supply')
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

# Preserve the complete five-role city and four-role production templates.
fac=L['facilities'];roads=L['roads'];hubs={h['owner']:h for h in L['hubs']};reserves=[f['reserved']for f in fac];ports=[]
for h in hubs.values():
 for fid in h['facilities'].values():
  f=next(f for f in fac if f['id']==fid);f['road_anchor']=h['node']
  if f['kind']=='road_depot':f.update(service_radius=400,maintenance_pool=12)
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
for i in I.values():
 if 'fishing_grounds'not in i['resource']:continue
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
   options.append((dst(p,i['position'])+dst(p,nodes[n])*1.5,p,dx,dy,n))
 if not options:raise ValueError('No fish coast '+str(i['id']))
 _,p,dx,dy,n=min(options,key=lambda x:x[0]);rot=math.degrees(math.atan2(dx,-dy))%360;fid='P'+str(i['id']);shore=pt(p['x']+dx*15,p['y']+dy*15)
 # Fine native coastal adjustment is performed separately; store the full alternative set.
 wh=pt(p['x']-dx*80,p['y']-dy*80);tr=pt(wh['x']-dy*75,wh['y']+dx*75)
 if not clear(box(tr,35)):
  tr=pt(wh['x']+dy*75,wh['y']-dx*75)
 wf=add(fid+'_warehouse','warehouse',wh,rot,'build_warehouse',{'module_count':1},30,owner=fid,road_required=False)
 tf=add(fid+'_truck','truck',tr,rot,'build_station',{'cargo':True,'size':1},35,owner=fid);access(tf,n)
 port=dict(id=fid+'_harbor',kind='harbor',industry=i['id'],position=shore,rotation=rot,water_direction=pt(dx,dy),warehouse=wf['id'],truck=tf['id'],node=n,shoreline_revision='native_small_pier_v1',candidates=[{'position':v,'water_direction':pt(a,b),'node':nn}for _,v,a,b,nn in sorted(options,key=lambda x:x[0])[:80]],waterRoute=waterpath(i['position'],shore),status='requires_fine_coast_preview')
 ports.append(port);reserves.append(box(shore,45));pos[fid]=tr
 for r in []:
  if r['source']==i['id']:
   rd,rp=shortest(n,nearest(pos[r['destination']]));r['road_edges']=rp;r['path'][0]=tr;r['mode']='HELICOPTER'if rd is None or rd/11+90>650 else'TRUCK'
# HQ: central dead end first, aligned along the existing end tangent.
focus=min(T,key=lambda tid:dst(T[tid]['position'],{'x':(S['bounds']['min']['x']+S['bounds']['max']['x'])/2,'y':(S['bounds']['min']['y']+S['bounds']['max']['y'])/2}));target=T[focus]['position'];hq=None
for n in sorted((n for n in nodes if len(adj[n])==1 and dst(nodes[n],target)<950),key=lambda n:dst(nodes[n],target)):
 other=adj[n][0][0];a=nodes[n];v=pt(a['x']-nodes[other]['x'],a['y']-nodes[other]['y']);length=math.hypot(v['x'],v['y']);rot=math.degrees(math.atan2(-v['x'],v['y']))%360
 for advance in [65,85,105]:
  p=pt(a['x']+v['x']/length*advance,a['y']+v['y']/length*advance)
  if clear(box(p,50)):
   hq=add('HQ','headquarters',p,rot,'build_headquarters',{'town':focus},50,town_name=T[focus]['name']);access(hq,n);break
 if hq:break
if not hq:raise ValueError('No HQ road end')
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

# Keep successful read-only coast refinements on the same current map.
prior=json.loads((R/'refined_baseline.json').read_text('utf8'))if(R/'refined_baseline.json').exists()else None
if prior:
 assert prior['session']['player']==S['state']['player']
 for port in ports:
  old=next((x for x in prior['ports']if x['id']==port['id']),None)
  if old and old.get('native_preview',{}).get('previewPassed'):port.update(old)
# Small-ship purchase/maintenance at each independent fishing shore.
for port in ports:
 p=port['position'];dx,dy=port['water_direction']['x'],port['water_direction']['y']
 depotpos=pt(p['x']-dy*110,p['y']+dx*110)
 f=add(port['id']+'_shipyard','water_depot',depotpos,port['rotation'],'native_construction',{},40,owner='P'+str(port['industry']),service_radius=800,maintenance_pool=4)
 if prior:
  old=next((x for x in prior['facilities']if x['id']==f['id']),None)
  if old and old.get('native_preview',{}).get('previewPassed'):f.update(old)
 port.update(command='native_construction',args={},footprint=box(p,45),reserved=box(p,60),purchase_base=f['id'])

coast=json.loads((R/'coast_layout.json').read_text('utf8'))if(R/'coast_layout.json').exists()else None
if coast:
 keep={x['industry']for x in coast['ports']};removed={f['id']for f in fac if f['kind']=='water_depot'or(f.get('owner','').startswith('P')and int(f['owner'][1:])not in keep)}
 fac[:]=[f for f in fac if f['id']not in removed];roads[:]=[r for r in roads if r.get('to_facility')not in removed];ports=coast['ports'];fac.append(coast['depot'])
 for port in ports:port['purchase_base']=coast['depot']['id']
else:
 # One purchase base candidate per connected water body. Native shoreline/path
 # checks still required; avoid three identical shipyards before those checks.
 regional=collections.defaultdict(list)
 for port in ports:regional[watercomponents.get(cell(I[port['industry']]['position']),port['industry'])].append(port)
 retain=set()
 for group in regional.values():
  chosen=min(group,key=lambda x:sum(dst(x['position'],y['position'])for y in group))['purchase_base'];retain.add(chosen)
  for port in group:port['purchase_base']=chosen
 fac[:]=[f for f in fac if f['kind']!='water_depot'or f['id']in retain]
fm={f['id']:f for f in fac};pm={p['industry']:p for p in ports};routes=[]
if coast:
 for source,target in coast['source_aliases'].items():pm[int(source)]=pm[target]
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
  chain.append(dict(mode='SMALL_SHIP',**{'from':src,'to':port['id']},warehouse=port['warehouse']));src=port['truck']
  if mode=='HELICOPTER':
   # Reuse the closest production collection that is reachable on the same land graph.
   choices=[h for h in hubs.values()if shortest(port['node'],h['node'])[0]is not None and not same_hub(h,hb)]
   if choices:ha=min(choices,key=lambda h:shortest(port['node'],h['node'])[0]);chain.append(dict(mode='TRUCK',**{'from':src,'to':ha['facilities']['truck']},warehouse=ha['facilities']['warehouse']))
   else:mode='UNRESOLVED_LAND_CONNECTION'
 if mode=='HELICOPTER':
  if ha and not port:chain.append(dict(mode='TRUCK',**{'from':src,'to':ha['facilities']['truck']},warehouse=ha['facilities']['warehouse']))
  chain.append(dict(mode='HELICOPTER',**{'from':air(ha)if ha else src,'to':air(hb)},source_second=air(ha,True)if ha else None,destination_second=air(hb,True),warehouse=hb['facilities']['warehouse'],maintenance_base=next(h['facilities']['heliport']for h in hubs.values()if h['kind']=='city')))
  chain.append(dict(mode='TRUCK',**{'from':hb['facilities']['truck'],'to':dstend}))
 else:chain.append(dict(mode='TRUCK',**{'from':src,'to':dstend}))
 routes.append(dict(id='R%03d'%j,**l,mode=mode,path=[pa,pb],road_edges=rp,transfer_chain=chain,alternatives={'road_seconds':rt,'air_seconds':at,'basis':'11m/s road;45m/s air;330s transfer estimate'},native_path_verified=False))

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
  lines.append(dict(id='LINE%03d'%(len(lines)+1),mode=m['mode'],source=src,destination=dest,cargos=cargo,flows=m['flows'],path=[p0,p1],warehouse=m.get('warehouse'),load_at_source=cid,load_at_destination=[],unload_at_destination=cid,cargo_index_offset=1,return_to_source=True,source_terminal_index=lane if src==m['from']and split else 0,destination_terminal_index=lane if dest==m['to']and split else 0,terminal_gate='resolve current station+terminal; distinct pad entities or distinct landing terminals; block if unsupported',parallel_split=count,capacity_forecast=cap,oneway_seconds_forecast=forecast,fleet_forecast=max(1,math.ceil(total/count*1.25*2*forecast/(1460*cap))),vehicle_model='::/vehicle/helicopter/piasecki_h21/piasecki_h21.mdl'if m['mode']=='HELICOPTER'else'::/vehicle/ship/votrans_universal/votrans_universal.mdl'if m['mode']=='SMALL_SHIP'else'::/vehicle/truck/gmc_660_dfm/gmc_660_dfm_univ.mdl',deadline_seconds=min(C[c]['timeToDeliverInSeconds']for c in cid),forecast_only=True))

# Service endpoints, not every metre of road. New fields remain forecasts until readback.
selected=[f for f in fac if f['kind']=='road_depot'];uncovered=[l for l in lines if l['mode']=='TRUCK'and not any(min(dst(location(l['source']),f['position']),dst(location(l['destination']),f['position']))<350 for f in selected)]
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
for owner in sorted({v['hub_owner']for v in L.get('shared_industry_hubs',{}).values()}):
 h=hubs[owner];members=set(h['facilities'].values());traffic=[]
 for line in lines:
  for end in ('source','destination'):
   if isinstance(line[end],str)and line[end]in members:
    traffic.append(dict(line=line['id'],direction=end,mode=line['mode'],cargos=line['cargos']))
 plan['shared_hub_capacity_review'].append(dict(owner=owner,industries=[int(i)for i,v in L['shared_industry_hubs'].items()if v['hub_owner']==owner],traffic=traffic,capacity_verified=False,required_checks=['industry round-trip road path','common warehouse stock','aggregate storage and truck terminal throughput','two landing terminals and fleet capacity'],note='Directional handling forecasts; do not sum both ends as additional supply. Expand or restore separate production hub if capacity fails.'))
fm={f['id']:f for f in fac+ports};known=set(fm)|{r['id']for r in roads}|{st['id']for st in stops}
jobs=[]
for f in fac+ports:jobs.append(dict(f,stage='facility',depends_on=[],authorization='not_granted'))
for stage,rows in [('road',roads),('street_stop',stops),('line',lines)]:
 for row in rows:
  deps=row.get('depends_on',[])if stage!='line'else sorted({v for v in [row['source'],row['destination'],row.get('warehouse')]if isinstance(v,str)and v in known}|{r['id']for r in roads if r.get('to_facility')in[row['source'],row['destination']]}|{x for v in[row['source'],row['destination']]if isinstance(v,dict)for x in v.get('unload_stops',[])})
  jobs.append(dict(id=row['id'],stage=stage,spec=row,depends_on=deps,authorization='not_granted'))
manifest=dict(schema=1,session={'player':S['state']['player'],'towns':S['map']['towns'],'industries':S['map']['industries']},jobs=jobs,commit_enabled=False,execution_policy='fresh session+late-bound entity/port -> native preview -> single commit after authorization -> bidirectional paths+catchment+inventory -> save')
write_json(R/'network_plan.json',plan);write_json(R/'execution_manifest.json',manifest)
print(json.dumps({'facilities':len(fac),'ports':len(ports),'roads':len(roads),'lines':len(lines),'stops':len(stops),'supply':supply,'seconds':time.time()-started},ensure_ascii=True))
