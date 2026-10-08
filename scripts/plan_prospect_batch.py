"""Authorized missing-supply prospection; same-request tickets, journal before dispatch."""
import argparse,asyncio,json,time
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json
from fullmap_batch import save_signature,quote
async def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args();out=a.output
 jpath=out/'prospection_journal.json';assert not jpath.exists()or a.resume,'Existing journal; reconcile only'
 b=Bridge();assert b.heartbeat().get('connected')
 source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+source+']========],"=prospect_batch","t",env))()._internal;'
 async def call(code,engine=True):
  r=await b.call('eval',{'code':(pre if engine else '')+code},engine=engine,timeout=45);return json.loads(r)if isinstance(r,str)else r
 with batch_lock(b.dir):
  state=await call('return B.json.encode(B.commands.get_game_state({}))');j=json.loads(jpath.read_text('utf8'))if jpath.exists()else {'state':state,'startedWall':time.time(),'operations':[]};assert state['player']==j['state']['player'];write_json(jpath,j)
  name='tf3_huaihua_prospect_before_20261004';path=b.dir.parent/'save'/(name+'.sav');before=save_signature(path)
  await call('app.saveGame("'+name+'",function()end,false,true);return {requested=true}',False)
  last=None
  for _ in range(60):
   sig=save_signature(path)
   if sig and sig!=before and sig==last:break
   last=sig;await asyncio.sleep(.5)
  else:raise RuntimeError('Backup unconfirmed')
  j['backup']={'path':str(path),'signature':sig};write_json(jpath,j)
  for row in json.loads(a.plan.read_text('utf8')):
   existing=next((r for r in j['operations']if r['cargo']==row['cargo']and r['town']==row['town']),None)
   if existing:
    q=await call('return B.json.encode(B.commands.get_prospections({}))')
    matches=[p for p in q['pending']if p['town']==row['town']and p['cargo'].endswith('/'+row['cargo']+'.cargo')]
    assert len(matches)==1,'Existing task not reconciled; do not resubmit'
    existing['nativePendingReconciliation']=matches[0];write_json(jpath,j);continue
   r=dict(row,attempted=True);j['operations'].append(r);write_json(jpath,j)
   args={'town':row['town'],'resource':'::/game_mechanics/company/explorations/exploration_'+row['cargo']+'.res'}
   code='local s=B.commands.get_game_state({});assert(s.player=='+str(state['player'])+',"Wrong map");local p=B.commands.preview_prospection(B.json.decode('+quote(args)+'));local r=B.commands.commit_prospection({preview_token=p.preview_token});return B.json.encode(r)'
   r['result']=await call(code);write_json(jpath,j)
   print(json.dumps(r),flush=True)
   if not r['result'].get('verified'):
    q=await call('return B.json.encode(B.commands.get_prospections({}))')
    matches=[p for p in q['pending']if p['town']==row['town']and p['cargo'].endswith('/'+row['cargo']+'.cargo')]
    assert len(matches)==1,'Unconfirmed; reconcile without retry'
    r['nativePendingReconciliation']=matches[0];write_json(jpath,j)
  j['dispatchFinishedWall']=time.time();write_json(jpath,j)
asyncio.run(main())
