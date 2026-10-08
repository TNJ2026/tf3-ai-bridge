"""Read-only whole-map primary-warehouse acceptance and deduplicated capacity."""
import argparse,asyncio,json
from pathlib import Path
from fullmap_batch import Batch,PLAN,ROOT,quote,batch_lock,write_json
from primary_warehouse import prelude,inventory_totals

def requests(plan):
 rows=[]
 for h in plan['hubs']:
  roles=h['facilities'];targets={k:roles[k]for k in ('truck','heliport','helipad','helipad2')if k in roles}
  if 'truck'not in targets or not any(k in targets for k in ('heliport','helipad')):raise ValueError('Missing hub cargo roles')
  rows.append(dict(id=str(h['owner']),kind='hub',warehouse=roles['warehouse'],targets=targets,primaryStockList=h.get('primaryStockList')))
 for p in plan['ports']:
  targets={'harbor':p['id']}
  if p.get('shared_stock_with'):targets['truck']=p['shared_stock_with']
  else:
   for role in ('helipad','helipad2'):targets[role]=p[role]
  rows.append(dict(id=p['id'],kind='port',warehouse=p['warehouse'],targets=targets,primaryStockList=p.get('primaryStockList')))
 return rows

async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--plan',type=Path,default=PLAN);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 a.action='verify';a.ids=None;a.limit=0;b=Batch(a)
 with batch_lock(b.b.dir):
  await b.session();tasks=b.tasks();checks=requests(b.p)
  code=prelude()+'''local tasks=B.json.decode(TASKS);local requests=B.json.decode(REQUESTS)
local CT=api.type.ComponentType;local rows={};local entities={};local out={hubs={},ports={}}
api.engine.forEachEntityWithComponent(function(id)local c=api.engine.getComponent(id,CT.CONSTRUCTION);local v=c.transf:cols(3);rows[#rows+1]={id=id,x=v.x,y=v.y}end,CT.CONSTRUCTION)
for _,t in ipairs(tasks)do
 for _,r in ipairs(rows)do if math.abs(r.x-t.position.x)<.2 and math.abs(r.y-t.position.y)<.2 then
  assert(not entities[t.id],'Ambiguous facility');entities[t.id]=r.id
 end end
end
for _,q in ipairs(requests)do
 local targets={};local missing=not entities[q.warehouse]
 for role,id in pairs(q.targets)do targets[role]=entities[id];missing=missing or not targets[role]end
 local r={id=q.id,warehouse=q.warehouse,verified=false,reason='facility_missing'}
 if not missing then r=primaryWarehouse(entities[q.warehouse],targets,q.primaryStockList);r.id=q.id;r.warehouse=q.warehouse end
 local bucket=q.kind=='hub'and out.hubs or out.ports;bucket[#bucket+1]=r
end
return B.json.encode(out)'''.replace('TASKS',quote(tasks)).replace('REQUESTS',quote(checks))
  r=await b.eval(code);audits=r['hubs']+r['ports']
  r['failedCoverage']=[v['id']for v in audits if not v['verified']]
  r['allCoverageVerified']=bool(audits)and not r['failedCoverage']
  r['inventoryTotals']=inventory_totals([v for v in audits if 'inventoryById'in v])
  r['operationalAccepted']=False;write_json(b.out/'hub_coverage.json',r);b.flush()
  print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
