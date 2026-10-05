"""Read-only, bounded city consumption and fleet health snapshot; never changes game speed."""
import argparse,asyncio,json,datetime
from pathlib import Path
from read_plan_inputs import INVENTORY,BUILDINGS
from fullmap_batch import ROOT,quote,batch_lock,write_json
from batch_warehouses import Bridge,fingerprint

async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 bridge=Bridge();assert bridge.heartbeat().get('connected'),'Bridge unavailable'
 source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf8')
 prefix='local env=setmetatable({},{__index=_G});local B=assert(load([========['+source+']========],"=health_read","t",env))()._internal;'
 async def read(code):
  value=await bridge.call('eval',{'code':prefix+code},engine=True,timeout=45)
  return json.loads(value)if isinstance(value,str)else value
 with batch_lock(bridge.dir):
  plan=json.loads(a.plan.read_text(encoding='utf8'));world=await read('return B.json.encode(B.commands.get_map_info({}))')
  expected={'towns':plan['cities'],'industries':[dict(i,fileName=i['resource'])for i in plan['industries']]}
  actual_fp=set(fingerprint(world));expected_fp=set(fingerprint(expected))
  assert {v for v in actual_fp if v[0]=='town'}=={v for v in expected_fp if v[0]=='town'} and expected_fp<=actual_fp,'Map changed; do not reuse previous monitoring baseline'
  added=[list(v)for v in actual_fp-expected_fp]
  inv=await read(INVENTORY);assert inv['state']['player']==plan['session']['player'],'Player changed'
  population=await read('local out={};for _,t in ipairs(B.commands.get_map_info({}).towns)do local u=api.engine.util.town.getTownCapacityUsage(t.id);local r=u[api.type.enum.LandUseType.RESIDENTIAL+1];out[tostring(t.id)]={population=r.used,residentialCapacity=r.capacity,busEligible=r.used>=150}end;return B.json.encode(out)')
  template=BUILDINGS.replace('dem[tostring(c.id)]=v','dem[tostring(c.id)]={demand=v,consumed=api.engine.util.stock.getCargoConsumedPerYear(b.stockList,c.id),delivered=api.engine.util.stock.getCargoTypeDeliveredPerYear(b.stockList,c.id)}')
  template=template.replace("local b=assert(api.engine.getComponent(row.id,CT.TOWN_BUILDING),'Building changed');assert(b.town==row.town,'Town changed');local dem={}","local b=api.engine.entityExists(row.id) and api.engine.getComponent(row.id,CT.TOWN_BUILDING);if not b or b.town~=row.town then out[#out+1]={id=row.id,town=row.town,skipped=true} else local dem={}")
  template=template.replace('demands=dem}\nend;', 'demands=dem}\nend end;')
  buildings=inv['buildings'];rows=[]
  chunks=[buildings[:8]]+[buildings[k:k+50]for k in range(8,len(buildings),50)]
  for chunk in chunks:
   if chunk:rows+=await read(template.replace('ROWS',quote(chunk)).replace('CARGOS',quote(inv['cargos'])).replace('PLAYER',str(inv['state']['player'])))
  fleet_source=(ROOT/'scripts/fleet_audit.lua').read_text(encoding='utf8')
  fleet_source=fleet_source.replace("n.name:find('全图供给·',1,true)==1", "(n.name:find('全图供给·',1,true)==1 or n.name:find('人口公交·',1,true)==1)")
  fleet=await read(fleet_source)
  cities={str(c['id']):dict(name=c['name'],buildings=0,cargos={},**population[str(c['id'])])for c in world['towns']}
  names={str(c['id']):c['name']for c in inv['cargos']}
  for row in rows:
   if row.get('skipped'):continue
   city=cities[str(row['town'])];city['buildings']+=1
   for cargo,data in (row['demands']or {}).items():
    aggregate=city['cargos'].setdefault(cargo,dict(name=names[cargo],demand=0,consumed=0,delivered=0))
    for field in ('demand','consumed','delivered'):aggregate[field]+=data[field]
  for city in cities.values():
   for data in city['cargos'].values():data['consumptionRatio']=data['consumed']/data['demand']if data['demand']else None
  # Persist unserved new cargo demand across samples; a one-sample diff loses
  # waiting work. This registry is read-only with respect to the game.
  watch_path=a.output/'supply_watch.json'
  identity=sorted([list(v)for v in expected_fp])
  if watch_path.exists():
   watch=json.loads(watch_path.read_text(encoding='utf8'))
   assert watch['mapIdentity']==identity,'Supply watch belongs to another map'
  else:
   baseline=cities
   for path in sorted(a.output.glob('20*T*.json')):
    sample=json.loads(path.read_text(encoding='utf8'))
    if 'cities'in sample:baseline=sample['cities'];break
   watch=dict(mapIdentity=identity,baseline={v['name']:list(v['cargos'])for v in baseline.values()},pending={})
  now=datetime.datetime.now(datetime.timezone.utc).isoformat()
  for city in cities.values():
   for cargo,data in city['cargos'].items():
    if data['demand']<=0 or cargo in watch['baseline'].get(city['name'],[]):continue
    key=city['name']+':'+cargo
    row=watch['pending'].setdefault(key,dict(city=city['name'],cargo=cargo,name=data['name'],status='needs_supply_check',firstSeen=now))
    row.update(lastSeen=now,demand=data['demand'],consumed=data['consumed'])
  write_json(watch_path,watch)
  vehicles=fleet['vehicles'];summary=dict(lines=len(fleet['lines']),vehicles=len(vehicles),
   noPath=[v['id']for v in vehicles if v['noPath']],stopped=[v['id']for v in vehicles if v['userStopped']],
   maintenanceLow=[dict(id=v['id'],line=v['line'],state=min(p['maintenanceState']for p in v['parts']))for v in vehicles if any(p['maintenanceState']<.5 for p in v['parts'])],
   noCurrentMaintenance=sum(v['maintenanceStation']<0 for v in vehicles),problems=fleet['problems'])
  out=dict(observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),newSupplyDemands=watch['pending'],skippedBuildings=[r for r in rows if r.get('skipped')],mapAdditions=added,stateStart=inv['state'],stateEnd=fleet['state'],cities=cities,summary=summary,fleet=fleet,
   limits=['Consumption/delivery are annualized engine statistics, not a full-year observation.','Batches are not an atomic snapshot while simulation runs.','No current maintenance assignment alone does not prove a fault.','Warehouse backlog and population health are not measured by this snapshot.'])
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');write_json(a.output/(stamp+'.json'),out);write_json(a.output/'latest.json',out)
  print(json.dumps(dict(cities=cities,summary=summary,state=fleet['state']),ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
