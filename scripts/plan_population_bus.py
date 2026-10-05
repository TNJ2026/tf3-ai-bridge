"""Read-only bus planning for explicitly named towns; reuse native passenger stops."""
import argparse,asyncio,json,math,itertools,hashlib
from pathlib import Path
from fullmap_batch import ROOT,batch_lock,write_json
from batch_warehouses import Bridge,fingerprint

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--towns',nargs='+',required=True);ap.add_argument('--identity-plan',type=Path,required=True);a=ap.parse_args()
 assert not(a.root/'plan.json').exists(),'Do not overwrite frozen plan'
 b=Bridge();src=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf8')
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+src+']========],"=bus_survey","t",env))()._internal;'
 with batch_lock(b.dir):
  r=await b.call('eval',{'code':pre+(ROOT/'scripts/bus_population_survey.lua').read_text(encoding='utf8')},engine=True,timeout=45)
 s=json.loads(r)if isinstance(r,str)else r;write_json(a.root/'survey.json',s)
 old=json.loads(a.identity_plan.read_text(encoding='utf8'));expected={'towns':old['cities'],'industries':[dict(i,fileName=i['resource'])for i in old['industries']]}
 assert set(fingerprint(expected))<=set(fingerprint(s['map'])),'Map changed'
 towns=[t for t in s['towns']if t['name']in a.towns];assert len(towns)==len(a.towns)
 allstops=[];specs=[];reviews=[]
 for town in towns:
  assert town['population']>=150,'Town below threshold'
  assert not any('人口公交·'+town['name']+'·'in l['name']for l in s['lines']['lines']),'Existing managed bus service; inspect rather than duplicate'
  bs=[b for b in s['buildings']if b['town']==town['id']];remaining={b['id']for b in bs};stops=[]
  for n in range(6):
   candidates=[]
   for e in s['roads']:
    if e['construction']>=0 or(e['objects']and e['passengerStops']!=2):continue
    p={k:(e['p0'][k]+e['p1'][k])/2 for k in ['x','y']}
    if math.hypot(p['x']-town['position']['x'],p['y']-town['position']['y'])>850:continue
    if any(math.dist(list(p.values()),list(t['position'].values()))<150 for t in stops):continue
    existing=e['passengerStops']==2
    covered=[b for b in bs if b['id']in e['catchables']]if existing else[b for b in bs if math.hypot(b['x']-p['x'],b['y']-p['y'])<150]
    score=sum(b['capacity']for b in covered if b['id']in remaining)
    candidates.append((score*(1.25 if existing else 1),e,p,covered,existing))
   if not candidates:break
   score,e,p,covered,existing=max(candidates,key=lambda c:c[0])
   if score<=0:break
   remaining-={b['id']for b in covered}
   stops.append(dict(id='BUS_'+str(town['id'])+'_STOP'+str(n+1),position=p,edge_endpoints=[e['p0'],e['p1']],param=.5,side='right',kind='auto',two_sided=True,covered_building_hints=[b['id']for b in covered],existing=existing))
   if len(stops)>=3 and len(remaining)<=len(bs)*.07:break
  assert len(stops)>=3,'Insufficient service coverage'
  order=min(itertools.permutations(stops[1:]),key=lambda perm:sum(math.dist(list(x['position'].values()),list(y['position'].values()))for x,y in zip([stops[0]]+list(perm),list(perm)+[stops[0]])))
  ordered=[stops[0]]+list(order)
  for d,label,seq in [('A','市区环线正向',ordered),('B','市区环线反向',list(reversed(ordered)))]:
   specs.append(dict(id='BUS_'+str(town['id'])+'_'+d,name='人口公交·'+town['name']+'·'+label,mode='BUS',endpoints=[dict(id=t['id'],stop=t,loads=[0])for t in seq]))
  allstops+=stops;reviews.append(dict(town=town['name'],population=town['population'],stops=len(stops),reuse=sum(t['existing']for t in stops),estimatedCovered=len(bs)-len(remaining),buildings=len(bs),basis='existing stops use native catchment; new stops 150m estimate; native routes mandatory'))
 plan=dict(cities=s['map']['towns'],industries=[dict(i,resource=i['fileName'])for i in s['map']['industries']],session=s['state'],facilities=[dict(id='DEPOT_'+str(d['id']),kind='road_depot',position=d['position'])for d in s['depots']if '/road_depot/'in d['resource']],ports=[],city_stops=[t for t in allstops if not t['existing']],reused_stops=[t for t in allstops if t['existing']],bus_specs=specs,reviews=reviews)
 write_json(a.root/'plan.json',plan)
 fleet=dict(planDigest=hashlib.sha256((a.root/'plan.json').read_bytes()).hexdigest(),lines=[dict(id=s['id'],count=2,model='urbangames_deluxe_upgrade_pack::/vehicle/bus/london_bus/london_bus.mdl',cargos=[0])for s in specs])
 write_json(a.root/'fleet.json',fleet);print(json.dumps(reviews,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
