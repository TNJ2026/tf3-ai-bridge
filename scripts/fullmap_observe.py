"""Bounded simulation observation; always pause afterward and preserve evidence."""
import argparse,asyncio,time,json
from types import SimpleNamespace
from fullmap_batch import *
async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=int,default=120);ap.add_argument('--speed',type=int,default=4);a=ap.parse_args()
 b=Batch(SimpleNamespace(plan=PLAN,output=ROOT/'exports/fullmap_plan_20261003/execution',action='verify',ids=None,limit=0));source=(ROOT/'scripts/fullmap_observe.lua').read_text(encoding='utf8');trace=[];tag=time.strftime('%Y%m%d_%H%M%S')
 with batch_lock(b.b.dir):
  await b.session();await b.save('fleet_observation_before')
  async def sample(full=False):
   s=await b.call('get_game_state');r=await b.eval(source.replace('if FULL then','if '+str(full).lower()+' then'));row=dict(state=s,audit=r,wall=time.time());trace.append(row);write_json(b.out/('observation_'+tag+'.json'),trace)
   print(json.dumps(dict(gameTime=s['gameTime'],vehicles=len(r['vehicles']),loaded=r['loaded'],noPath=r['noPath'],citiesWithSupply=sum(v['supply']>0 for v in r.get('townSupply',[]))if full else None),ensure_ascii=False),flush=True);return r
  await sample(True);await b.call('set_game_speed',dict(speed=a.speed))
  try:
   deadline=time.monotonic()+a.seconds
   while time.monotonic()<deadline:
    await asyncio.sleep(min(10,max(0,deadline-time.monotonic())));r=await sample()
    if r['noPath']:break
  finally:await b.call('set_game_speed',dict(speed=0))
  final=await sample(True);write_json(b.out/'current_operations.json',final)
  try:await b.session()
  except StopBatch:
   await b.save('fleet_observation_map_changed');raise
  await b.save('fleet_observation_after')
if __name__=='__main__':asyncio.run(main())
