"""Read back the new collection, shared stock, roads and passenger transfer; save natively."""
import asyncio,json
from types import SimpleNamespace
from build_displayed_collection import Copy,OUT
from hub_collection import Collection
from fullmap_batch import ROOT,quote,batch_lock,StopBatch
from batch_warehouses import write_json

async def accept_collection(b):
 tasks=b.tasks();rows=await b.read_facilities(tasks,'verify',with_session=True);entities={}
 for task,row in zip(tasks,rows):
  audit=row['result'].get('audit',{})
  if not audit.get('staticVerified'):raise StopBatch('Facility missing or changed')
  expected=task['expectedParams']['modules'];actual=audit['params']['modules']
  norm=lambda m:{k:(v['name'],v.get('variant',0))for k,v in m.items()}
  if norm(expected)!=norm(actual):raise StopBatch('Expansion modules mismatch')
  entities[task['kind']]=audit['entity']
 roads={};edges=[]
 for spec in b.p['roads']:
  item=b.ledger['items'][spec['id']];audit=await b.audit_road(item);item['audit']=audit
  roads[spec['id']]=audit['verified'];edges+=item.get('commit',{}).get('edges',[])
 code='''local f=B.json.decode(ENTITIES);local CT=api.type.ComponentType
local stocks={};local out={capacity=0,coverage={},links={}}
api.engine.forEachEntityWithComponent(function(id)local w=api.engine.getComponent(id,CT.WAREHOUSE);if w.construction==f.warehouse then stocks[w.stockList]=true;stocks[id]=true;for _,s in ipairs(api.engine.getComponent(w.stockList,CT.STOCK_LIST).stocks)do out.capacity=out.capacity+s.capacity end end end,CT.WAREHOUSE)
for _,role in ipairs({'heliport','truck'})do local covered=false;for _,st in ipairs(api.engine.getComponent(f[role],CT.CONSTRUCTION).stations)do for _,id in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(st,true))do covered=covered or stocks[id]==true end end;out.coverage[role]=covered end
local sc=api.engine.system.streetConnectorSystem;local seen={}
for _,ids in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities())do for _,id in ipairs(ids)do if not seen[id]then seen[id]=true;local l=api.engine.getComponent(id,CT.TP_NET_LINK);local a,b=l.from.edgeId.entity,l.to.edgeId.entity
if a==f.heliport or b==f.heliport or sc.getConstructionEntityForSubconstruction(a)==f.heliport or sc.getConstructionEntityForSubconstruction(b)==f.heliport then out.links[#out.links+1]={from=a,to=b}end
end end end
return B.json.encode(out)'''.replace('ENTITIES',quote(entities))
 result=await b.eval(code);result['entities']=entities;result['roads']=roads
 result['airportRoadLinkVerified']=any(r['from']in edges or r['to']in edges for r in result['links'])
 result['walking']=await Collection.passenger_audit(b,entities)
 result['staticAccepted']=all(roads.values())and all(result['coverage'].values())and result['airportRoadLinkVerified']and result['walking']['verified']
 result['operationalAccepted']=False
 write_json(b.out.parent/'result.json',result);b.ledger['acceptance']=result;b.flush();print(json.dumps(result),flush=True)
 if not result['staticAccepted']:
  await b.save('copy_static_checkpoint')
  result['save']=b.ledger['events'][-1];write_json(b.out.parent/'result.json',result)
  raise StopBatch('Construction saved; passenger walking acceptance remains unverified')
 await b.save('copy_complete');result['save']=b.ledger['events'][-1];write_json(b.out.parent/'result.json',result)
 return result

async def main():
 b=Copy(SimpleNamespace(plan=OUT/'plan.json',output=OUT/'execution',action='verify',ids=None,road_ids=None,limit=0))
 try:
  with batch_lock(b.b.dir):await accept_collection(b)
 finally:b.flush()
if __name__=='__main__':asyncio.run(main())
