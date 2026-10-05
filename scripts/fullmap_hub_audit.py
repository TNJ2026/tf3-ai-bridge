"""Read-only whole-map hub acceptance. Never interprets distance as shared cargo stock."""
import asyncio,json,sys
from pathlib import Path
from types import SimpleNamespace
from fullmap_batch import Batch,PLAN,ROOT,quote,batch_lock,write_json
async def main():
 b=Batch(SimpleNamespace(plan=PLAN,output=ROOT/'exports/fullmap_plan_20261003/execution',action='verify',ids=None,limit=0))
 with batch_lock(b.b.dir):
  await b.session()
  tasks=b.tasks();code='''local tasks=B.json.decode(TASKS);local CT=api.type.ComponentType;local out={facilities={},hubs={},ports={}};local rows={}
api.engine.forEachEntityWithComponent(function(id)local c=api.engine.getComponent(id,CT.CONSTRUCTION);local v=c.transf:cols(3);rows[#rows+1]={id=id,c=c,x=v.x,y=v.y}end,CT.CONSTRUCTION)
local warehouses={};api.engine.forEachEntityWithComponent(function(id)local w=api.engine.getComponent(id,CT.WAREHOUSE);warehouses[w.construction]=warehouses[w.construction]or{};table.insert(warehouses[w.construction],{entity=id,stockList=w.stockList})end,CT.WAREHOUSE)
for _,t in ipairs(tasks)do
 local matches={};for _,r in ipairs(rows)do if math.abs(r.x-t.position.x)<.2 and math.abs(r.y-t.position.y)<.2 then matches[#matches+1]=r end end
 if #matches==1 then
  local r=matches[1];local f={entity=r.id,resource=r.c.fileName,stocks=warehouses[r.id]or{},stations={},service={}}
  for _,id in ipairs(r.c.stations)do
   local st=api.engine.getComponent(id,CT.STATION);local term={};for _,q in ipairs(st.terminals)do term[#term+1]={load=q.cargoLoad,unload=q.cargoUnload,modes=B.toPlain(q.transportModes)}end
   f.stations[#f.stations+1]={id=id,catchables=B.toPlain(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true)),terminals=term}
  end
  for _,id in ipairs(r.c.depots)do local d=api.engine.getComponent(id,CT.VEHICLE_DEPOT);if d then f.service[#f.service+1]={id=id,pool=d.maintenancePool,radius=d.catchmentArea and d.catchmentArea.radius,modes=B.toPlain(d.transportModes)}end end
  out.facilities[t.id]=f
 end
end
return B.json.encode(out)'''.replace('TASKS',quote(tasks))
  r=await b.eval(code);f=r['facilities'];fail=[]
  def covered(station,warehouse):
   if station not in f or warehouse not in f:return False
   stockids={x[k]for x in f[warehouse]['stocks']for k in ['entity','stockList']}|{f[warehouse]['entity']}
   return any(set(s['catchables'])&stockids for s in f[station]['stations'])
  for h in b.p['hubs']:
   wh=h['facilities']['warehouse'];truck=h['facilities']['truck'];heli=h['facilities']['helipad']
   if wh not in f:continue
   row={'hub':h['owner'],'warehouse':wh,'truckCovered':covered(truck,wh),'helipadCovered':covered(heli,wh)};row['verified']=row['truckCovered']and row['helipadCovered'];r['hubs'].append(row)
   if not row['verified']:fail.append(h['owner'])
  for p in b.p['ports']:
   row={'port':p['id'],'portCovered':covered(p['id'],p['warehouse']),'truckCovered':covered(p['shared_stock_with'],p['warehouse'])};row['verified']=row['portCovered']and row['truckCovered'];r['ports'].append(row)
   if not row['verified']:fail.append(p['id'])
  r['failedCoverage']=fail;r['allCoverageVerified']=not fail;r['operationalAccepted']=False;write_json(b.out/'hub_coverage.json',r)
  print(json.dumps({'facilities':len(f),'hubs':r['hubs'],'ports':r['ports'],'failed':fail},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
