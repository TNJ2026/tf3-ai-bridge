"""Bounded, read-only current industry recipes and production evidence."""
import argparse,asyncio,json,datetime
from pathlib import Path
from fullmap_batch import ROOT,quote,batch_lock,write_json
from batch_warehouses import Bridge,fingerprint

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 b=Bridge();assert b.heartbeat().get('connected')
 src=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf8')
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+src+']========],"=supply_inspection","t",env))()._internal;'
 async def read(code):
  r=await b.call('eval',{'code':pre+code},engine=True,timeout=45)
  return json.loads(r)if isinstance(r,str)else r
 with batch_lock(b.dir):
  world=await read('return B.json.encode({map=B.commands.get_map_info({}),state=B.commands.get_game_state({})})')
  p=json.loads(a.plan.read_text(encoding='utf8'));expected={'towns':p['cities'],'industries':[dict(i,fileName=i['resource'])for i in p['industries']]}
  actual=set(fingerprint(world['map']));old=set(fingerprint(expected))
  assert old<=actual and {v for v in old if v[0]=='town'}=={v for v in actual if v[0]=='town'},'Different map'
  out=dict(observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),stateStart=world['state'],industries=[])
  code='''local rows=B.json.decode(ROWS);local CT=api.type.ComponentType;local out={}
for _,row in ipairs(rows)do
 local i=api.engine.entityExists(row.id)and api.engine.getComponent(row.id,CT.INDUSTRY)
 local r={id=row.id,resource=row.fileName,position=row.position}
 if i and i.stockList>=0 and api.engine.entityExists(i.stockList)and api.engine.getComponent(i.stockList,CT.STOCK_LIST)then
  local sl=api.engine.getComponent(i.stockList,CT.STOCK_LIST);local io=api.engine.util.stock.getInputsOutputsFromRules(i.stockList)
  r.inputs={};r.outputs={};r.rules={}
  for _,k in ipairs(io[1])do r.inputs[#r.inputs+1]={cargo=k,name=api.res.cargoTypeRep.get(k).name,capacity=api.engine.util.stock.getCargoMaxConsumptionPerYear(i.stockList,k),consumed=api.engine.util.stock.getCargoConsumedPerYear(i.stockList,k)}end
  for _,k in ipairs(io[2])do r.outputs[#r.outputs+1]={cargo=k,name=api.res.cargoTypeRep.get(k).name,capacity=api.engine.util.stock.getCargoMaxProductionPerYear(i.stockList,k),produced=api.engine.util.stock.getCargoProducedPerYear(i.stockList,k),shipped=api.engine.util.stock.getCargoTypeShippedPerYear(i.stockList,k)}end
  for _,rule in ipairs(sl.rules)do r.rules[#r.rules+1]={input=B.toPlain(rule.input),output=B.toPlain(rule.output),capacity=rule.capacity,booster=rule.booster}end
 else r.unavailable='no valid industry stock list'end
 out[#out+1]=r
end;return B.json.encode(out)'''
  industries=world['map']['industries']
  for k in range(0,len(industries),4):
   out['industries']+=await read(code.replace('ROWS',quote(industries[k:k+4])));write_json(a.output,out)
  out['stateEnd']=await read('return B.json.encode(B.commands.get_game_state({}))');write_json(a.output,out)
  print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
