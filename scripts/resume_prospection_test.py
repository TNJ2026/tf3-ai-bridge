"""Read native progress for an already-submitted test; contains no commit command."""
import asyncio,json,time,uuid
from fullmap_batch import Bridge,batch_lock,write_json,ROOT
async def main():
 b=Bridge();out=ROOT/'exports/prospection_live_20261003_124135';report=json.loads((out/'report.json').read_text(encoding='utf8'));town=report['town']['id'];cargo='::/cargos/vegetables/vegetables.cargo';start=report['commit']['started_at']
 def flush():write_json(out/'report.json',report)
 async def call(cmd,args=None,engine=True):
  r=await b.call(cmd,args or {},engine=engine,timeout=45);return json.loads(r)if isinstance(r,str)else r
 with batch_lock(b.dir):
  status=await call('get_prospections');assert any(p['town']==town and p['cargo']==cargo and p['started_at']==start for p in status['pending'])
  report['tracking_receipt']={'id':report['commit']['operation_id'],'session':status['session'],'town':next(p['town_ref']for p in status['pending']if p['town']==town and p['cargo']==cargo),'cargo':cargo,'previousNotifications':{},'registered':True};report['tracking_receipt']['session']['gameTime']=start;flush()
  await call('set_game_speed',{'speed':4})
  try:
   deadline=time.monotonic()+190
   while time.monotonic()<deadline:
    await asyncio.sleep(10);status=await call('get_prospections');report['samples'].append({'status':status});flush();print(json.dumps(status,ensure_ascii=False),flush=True)
    found=[h for h in status['history']if h['town']==town and h['cargo']==cargo and h['timestamp']>=start]
    if found:report['native_result']=found;break
  finally:
   await call('set_game_speed',{'speed':0});report['after_state']=await call('get_game_state');report['final_status']=await call('get_prospections');write_json(out/'world_after.json',await call('get_map_info'));flush()
   name='tf3_prospection_result_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6];file=b.dir.parent/'save'/(name+'.sav')
   await call('eval',{'code':'app.saveGame('+json.dumps(name)+',function() end,false,true);return {requested=true}'},False)
   prev=None
   for _ in range(60):
    if file.exists():
     st=file.stat();v=(st.st_size,st.st_mtime_ns)
     if prev==v and st.st_size>0:report['saves'].append({'name':name,'file':str(file),'complete':True});flush();break
     prev=v
    await asyncio.sleep(.5)
   print('RESULT '+json.dumps(report.get('native_result'),ensure_ascii=False),flush=True)
if __name__=='__main__':asyncio.run(main())
