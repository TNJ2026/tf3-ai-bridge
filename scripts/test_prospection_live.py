"""One authorized live prospecting test. Journal before dispatch; never auto retry."""
import asyncio,json,time,uuid
from fullmap_batch import Bridge,batch_lock,write_json,ROOT
async def main():
 b=Bridge();out=ROOT/'exports'/('prospection_live_'+time.strftime('%Y%m%d_%H%M%S'));out.mkdir();report={'commit_attempts':0,'samples':[],'saves':[]}
 def flush():write_json(out/'report.json',report)
 async def call(cmd,args=None,engine=True):
  r=await b.call(cmd,args or {},engine=engine,timeout=45)
  return json.loads(r)if isinstance(r,str)else r
 async def save(phase):
  name='tf3_prospection_'+phase+'_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
  file=b.dir.parent/'save'/(name+'.sav');report['saves'].append({'name':name,'file':str(file),'complete':False});flush()
  await call('eval',{'code':'app.saveGame('+json.dumps(name)+',function() end,false,true);return {requested=true}'},False)
  prev=None
  for _ in range(60):
   if file.exists():
    st=file.stat();now=(st.st_size,st.st_mtime_ns)
    if now==prev and st.st_size>0:report['saves'][-1]['complete']=True;flush();return
    prev=now
   await asyncio.sleep(.5)
  raise RuntimeError('Save completion unknown; stop')
 with batch_lock(b.dir):
  assert b.heartbeat()['connected'];state=await call('get_game_state');report['before_state']=state
  world=await call('get_map_info');write_json(out/'world_before.json',world)
  town=next(t for t in world['towns']if t['name']=='自贡');report['town']=town
  await call('set_game_speed',{'speed':0});await save('before')
  p=await call('preview_prospection',{'town':town['id'],'resource':'::/game_mechanics/company/explorations/exploration_vegetables.res'});report['preview']=p;flush()
  report['commit_attempts']=1;report['commit_state']='dispatching';flush()
  try:
   r=await call('commit_prospection',{'preview_token':p['preview_token']});report['commit']=r;report['commit_state']='returned';flush();print(json.dumps(r,ensure_ascii=False),flush=True)
   r=await call('get_prospection_operation',{'operation_id':p['preview_token'],'tracking_receipt':report['commit'].get('tracking_receipt')});report['readback']=r
   report['resources_after_commit']=await call('list_prospections');flush()
   assert r['verified'] and r['status']=='pending','Unverified submission: stop and reconcile, do not resend'
   # Verify same-town and shared-permit guards through previews only.
   report['blocked_previews']=[]
   for cargo in ['vegetables','grain']:
    try:
     v=await call('preview_prospection',{'town':town['id'],'resource':'::/game_mechanics/company/explorations/exploration_'+cargo+'.res'})
     report['blocked_previews'].append({'cargo':cargo,'unexpected_preview':v})
    except Exception as e:report['blocked_previews'].append({'cargo':cargo,'blocked':str(e)})
   flush();await call('set_game_speed',{'speed':4});deadline=time.monotonic()+210
   while time.monotonic()<deadline:
    await asyncio.sleep(10)
    status=await call('get_prospections');op=await call('get_prospection_operation',{'operation_id':p['preview_token'],'tracking_receipt':report['commit'].get('tracking_receipt')})
    report['samples'].append({'status':status,'operation':op});flush()
    print(json.dumps({'operation':op,'pending':status['pending']},ensure_ascii=False),flush=True)
    if op['status']in ['succeeded','failed','session_changed']:break
  except Exception as e:report['error']=str(e);flush();raise
  finally:
   await call('set_game_speed',{'speed':0})
   report['after_state']=await call('get_game_state');report['final_status']=await call('get_prospections')
   write_json(out/'world_after.json',await call('get_map_info'));await save('after');flush()
   print('REPORT '+str(out/'report.json'),flush=True)
   if state['speedup']!=0:await call('set_game_speed',{'speed':state['speedup']})
if __name__=='__main__':
 import sys
 if '--new-authorized-test' not in sys.argv:raise SystemExit('Historical live test: not resumable. Use read-only get_prospections for the existing submission. A fresh test needs --new-authorized-test and current authorization.')
 asyncio.run(main())
