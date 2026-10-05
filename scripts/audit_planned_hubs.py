"""Read-only collection modules, shared warehouse stock and airport-road links."""
import argparse,asyncio,json
from pathlib import Path
from fullmap_batch import Batch,quote,batch_lock,StopBatch,write_json
async def audit(b,owner):
 h=next(h for h in b.p['hubs']if h['owner']==owner);tasks=[t for t in b.tasks()if t.get('owner')==owner]
 rows=await b.read_facilities(tasks,'verify',with_session=True);entities={};audits={}
 for t,row in zip(tasks,rows):
  a=row['result'].get('audit',{});assert a.get('staticVerified'),t['id']
  norm=lambda m:{str(k):(v['name'],v.get('variant',0))for k,v in (m or {}).items()}
  assert norm(t['params'].get('modules',{}))==norm(a['params'].get('modules',{})),'Module mismatch'
  entities[t['kind']]=a['entity'];audits[t['kind']]=a
 code='''local f=B.json.decode(FAC);local CT=api.type.ComponentType;local out={stocks={},coverage={},links={}};local stocks={}
api.engine.forEachEntityWithComponent(function(id)local w=api.engine.getComponent(id,CT.WAREHOUSE);if w.construction==f.warehouse then stocks[id]=true;stocks[w.stockList]=true;out.stocks[#out.stocks+1]={entity=id,stockList=w.stockList}end end,CT.WAREHOUSE)
for _,role in ipairs({'truck','heliport','helipad','helipad2'})do if f[role]then local cc={};for _,st in ipairs(api.engine.getComponent(f[role],CT.CONSTRUCTION).stations)do for _,id in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(st,true))do if stocks[id]then cc[id]=true end end end;local rr={};for id in pairs(cc)do rr[#rr+1]=id end;out.coverage[role]=rr end end
if f.heliport then local sc=api.engine.system.streetConnectorSystem;local seen={};for _,ids in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities())do for _,id in ipairs(ids)do if not seen[id]then seen[id]=true;local l=api.engine.getComponent(id,CT.TP_NET_LINK);local a,c=l.from.edgeId.entity,l.to.edgeId.entity;if a==f.heliport or c==f.heliport or sc.getConstructionEntityForSubconstruction(a)==f.heliport or sc.getConstructionEntityForSubconstruction(c)==f.heliport then out.links[#out.links+1]={from=a,to=c}end end end end end
return B.json.encode(out)'''.replace('FAC',quote(entities))
 road_ids=list(h['roads']);extra_file=b.out/'extra_roads.json'
 if extra_file.exists():
  extras=json.loads(extra_file.read_text('utf8'))
  if extras['planDigest']!=b.ledger['planDigest']:raise StopBatch('Extra roads belong to another plan')
  road_ids += [r['id']for r in extras['roads']if r['id'].startswith(owner+'_')]
 v=await b.eval(code);sets=[set(ids)for ids in v['coverage'].values()];common=set.intersection(*sets)if sets else set();edgeids={e for rid in road_ids for e in b.ledger['items'].get(rid,{}).get('commit',{}).get('edges',[])}
 if 'heliport'in entities:
  helper=Path(__file__).with_name('station_walk_transfer.lua').read_text('utf8')
  walking=('''local f=B.json.decode(FAC);local CT=api.type.ComponentType
local function stations(role)local ids={};for _,id in ipairs(api.engine.getComponent(f[role],CT.CONSTRUCTION).stations)do ids[#ids+1]=id end;return ids end
local reach=api.engine.system.catchmentAreaSystem.getStation2stationsAndDistancesMap()
'''+helper+'''local a,b=transfer(stations('bus'),stations('heliport')),transfer(stations('heliport'),stations('bus'))
return B.json.encode({outbound=a,inbound=b,verified=a.verified and b.verified})''').replace('FAC',quote(entities))
  v['passengerWalking']=await b.eval(walking)
 v.update(owner=owner,entities=entities,commonWarehouseStockIds=sorted(common),modulesVerified=True,roadsRecordedVerified=all(b.ledger['items'].get(rid,{}).get('status')=='connection_verified'for rid in road_ids),airportRoadLinked=any(l['from']in edgeids or l['to']in edgeids for l in v['links'])if 'heliport'in entities else None,operationalAccepted=False)
 v['cargoStaticAccepted']=bool(common)and v['roadsRecordedVerified']and v['airportRoadLinked']is not False
 write_json(b.out/(owner+'_acceptance.json'),v);print(json.dumps({k:v.get(k)for k in ('owner','cargoStaticAccepted','commonWarehouseStockIds','passengerWalking','operationalAccepted')}))
 if not v['cargoStaticAccepted']:raise StopBatch('Collection acceptance incomplete '+owner)
 return v
async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--owner',required=True);a=ap.parse_args();a.action='verify';a.ids=None;a.limit=0;b=Batch(a)
 try:
  with batch_lock(b.b.dir):await audit(b,a.owner)
 finally:b.flush()
if __name__=='__main__':asyncio.run(main())
