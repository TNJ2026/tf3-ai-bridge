"""Bounded readback of native vehicle condition after maintenance construction."""
import asyncio,time,json
from types import SimpleNamespace
from repair_maintenance import MaintenanceBatch,OUT
from fullmap_batch import *
async def main():
 b=MaintenanceBatch(SimpleNamespace(plan=PLAN,output=OUT,action='verify',ids=None,limit=0));src=(ROOT/'scripts/maintenance_survey.lua').read_text(encoding='utf8').replace('TARGETS',quote([]));trace=[]
 with batch_lock(b.b.dir):
  initial=await b.session();await b.save('maintenance_observe_before')
  async def sample():
   r=await b.eval(src);trace.append(r);write_json(OUT/'observation.json',trace)
   low=[dict(line=v['lineName'],condition=round(v['condition']*100,1),change=v['change'],maintenance=v['maintenanceStation'])for v in r['vehicles']if v['condition']<=.8 or v['lineName'].split('·')[-1]in ['SHUTTLE49363','SHUTTLE49957','SHUTTLE16729','SHUTTLE50017','R012']]
   print(json.dumps({'time':r['state']['gameTime'],'noPath':sum(v['noPath']for v in r['vehicles']),'vehicles':low},ensure_ascii=False),flush=True);return r
  await sample();await b.call('set_game_speed',{'speed':4})
  try:
   for _ in range(12):
    await asyncio.sleep(10);r=await sample()
    if any(v['noPath']for v in r['vehicles']):break
  finally:
   await b.call('set_game_speed',{'speed':0});last=await sample();b.ledger['lastState']=last['state'];b.flush();await b.save('maintenance_recovery_after')
   if initial['speedup']!=0:await b.call('set_game_speed',{'speed':initial['speedup']})
if __name__=='__main__':asyncio.run(main())
