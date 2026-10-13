"""Bounded current-map demand/capacity reads; no historical export dependencies."""
import argparse,asyncio,json,time
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json
from fullmap_batch import quote

INVENTORY="""local CT=api.type.ComponentType;local m=B.commands.get_map_info({});local out={state=B.commands.get_game_state({}),industries={},buildings={},cargos={},frozenNodes={},stations={}}
for id,name in pairs(api.res.cargoTypeRep.getAll(true))do local c=api.res.cargoTypeRep.get(id);out.cargos[#out.cargos+1]={id=id,resource=name,name=c.name,timeToDeliverInSeconds=c.timeToDeliverInSeconds}end
api.engine.forEachEntityWithComponent(function(id)local c=api.engine.getComponent(id,CT.CONSTRUCTION);for _,n in ipairs(c.frozenNodes)do out.frozenNodes[#out.frozenNodes+1]=n end end,CT.CONSTRUCTION)
local buildingMap=api.engine.system.townBuildingSystem.getTown2BuildingMap()
out.townSupply={}
for _,town in ipairs(m.towns) do
 out.townSupply[tostring(town.id)]=B.commands.get_town_cargo_supply({town=town.id})
 for _,id in pairs(buildingMap[town.id] or {}) do out.buildings[#out.buildings+1]={id=id,town=town.id} end
end
table.sort(out.buildings,function(a,b)return a.id<b.id end)
for _,i in ipairs(m.industries)do local c=assert(api.engine.getComponent(i.id,CT.INDUSTRY));local con=assert(api.engine.getComponent(c.construction,CT.CONSTRUCTION));out.industries[#out.industries+1]={id=i.id,resource=i.fileName,position=i.position,construction=c.construction,stations=B.toPlain(con.stations)}end
return B.json.encode(out)"""
BUILDINGS="""local CT=api.type.ComponentType;local rows=B.json.decode(ROWS);local townCargos=B.json.decode(TOWN_CARGOS);local out={}
assert(api.engine.util.getPlayer()==PLAYER,'Map changed')
for _,row in ipairs(rows)do
 local b=assert(api.engine.getComponent(row.id,CT.TOWN_BUILDING),'Building changed');assert(b.town==row.town,'Town changed');local dem={}
 if b.stockList>=0 and api.engine.entityExists(b.stockList) and api.engine.getComponent(b.stockList,CT.STOCK_LIST)then
  for _,c in ipairs(townCargos[tostring(row.town)] or {})do local v=api.engine.util.stock.getCargoMaxConsumptionPerYear(b.stockList,c);if v>0 then dem[tostring(c)]=v end end
 end
 out[#out+1]={id=row.id,town=row.town,demands=dem}
end;return B.json.encode(out)"""
CAPACITY="""local CT=api.type.ComponentType;local rows=B.json.decode(ROWS);local cargos=B.json.decode(CARGOS);local out={industries={}}
assert(api.engine.util.getPlayer()==PLAYER,'Map changed')
for _,row in ipairs(rows)do
 local i=assert(api.engine.getComponent(row.id,CT.INDUSTRY));assert(i.stockList>=0 and api.engine.entityExists(i.stockList) and api.engine.getComponent(i.stockList,CT.STOCK_LIST),'Invalid industry stock')
 local inputs,outputs={},{}
 for _,c in ipairs(cargos)do
  local v=api.engine.util.stock.getCargoMaxConsumptionPerYear(i.stockList,c.id);if v>0 then inputs[tostring(c.id)]=v end
  local w=api.engine.util.stock.getCargoMaxProductionPerYear(i.stockList,c.id);if w>0 then outputs[tostring(c.id)]=w end
 end
 out.industries[#out.industries+1]={id=row.id,inputs=inputs,outputs=outputs}
end;return B.json.encode(out)"""

async def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=Bridge();assert b.heartbeat().get('connected')
 source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+source+']========],"=planning_read","t",env))()._internal;'
 async def read(code):
  r=await b.call('eval',{'code':pre+code},engine=True,timeout=45);return json.loads(r)if isinstance(r,str)else r
 start=time.perf_counter()
 with batch_lock(b.dir):
  details=await read(INVENTORY);write_json(a.output/'inventory.json',details);buildings=details.pop('buildings');details['buildings']=[]
  def code(template,rows):return template.replace('ROWS',quote(rows)).replace('TOWN_CARGOS',quote({k:[r['cargo'] for r in v['items']] for k,v in details['townSupply'].items()})).replace('CARGOS',quote(details['cargos'])).replace('PLAYER',str(details['state']['player']))
  # Small first batch verifies the schema; later batches remain bounded.
  chunks=[buildings[:8]]+[buildings[k:k+100]for k in range(8,len(buildings),100)]
  for rows in chunks:
   if not rows:continue
   details['buildings']+=await read(code(BUILDINGS,rows));write_json(a.output/'details_partial.json',details)
  cap={'industries':[]}
  for k in range(0,len(details['industries']),4):cap['industries']+=(await read(code(CAPACITY,details['industries'][k:k+4])))['industries']
  write_json(a.output/'details.json',details);write_json(a.output/'capacity.json',cap)
  write_json(a.output/'input_read_times.json',{'seconds':time.perf_counter()-start,'buildingBatches':len(chunks),'buildings':len(buildings)})
  print(json.dumps({'buildings':len(buildings),'industries':len(cap['industries']),'seconds':time.perf_counter()-start}))
if __name__=='__main__':asyncio.run(main())
