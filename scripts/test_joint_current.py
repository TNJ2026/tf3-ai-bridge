"""One authorized joint preview on the current map, after a verified native backup."""
import asyncio,json,time,argparse
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json,StopBatch
from fullmap_batch import save_signature
from hub_joint_prototype import compile_spec,probe

async def main():
 b=Bridge();assert b.heartbeat().get('connected')
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'exports/joint_live_preview');parser.add_argument('--spec',type=Path);parser.add_argument('--offset-x',type=float,default=0);parser.add_argument('--offset-y',type=float,default=0);args=parser.parse_args()
 out=args.output;out.mkdir(exist_ok=True)
 if (out/'receipt.json').exists():raise StopBatch('Existing attempt: inspect receipt, do not replay')
 async def call(code,engine=True):
  r=await b.call('eval',{'code':code},engine=engine,timeout=45)
  return json.loads(r)if isinstance(r,str)else r
 with batch_lock(b.dir):
  camera=await call('local p=api.gui.camera.getCenter();return {x=p.x,y=p.y,z=p.z}',False)
  source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
  assert ']========]'not in source
  pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+source+']========],"=joint_test","t",env))()._internal;'
  state=await call(pre+'return B.json.encode(B.commands.get_game_state({}))')
  if state['speedup']!=0:raise StopBatch('Pause required for a consistent test')
  template=json.loads((ROOT/'exports/hub_template_displayed/template/hub_template.json').read_text('utf8'))
  origin=dict(camera,rotation=template['sourceEvidence']['rotation'])
  origin['x']+=args.offset_x;origin['y']+=args.offset_y
  if args.spec:
   placement=json.loads(args.spec.read_text('utf8')).get('placement')
   if placement:origin.update(placement)
  receipt={'authorization':'User explicitly overrode isolated-save restriction for this current-position test','origin':origin,'state':state,'submitted':False,'previewAttempted':False}
  name='tf3_joint_before_'+time.strftime('%Y%m%d_%H%M%S');path=b.dir.parent/'save'/(name+'.sav');before=save_signature(path)
  await call('app.saveGame("'+name+'",function()end,false,true);return {requested=true}',False)
  previous=None
  for _ in range(60):
   signature=save_signature(path)
   if signature and signature!=before and signature==previous and signature[0]>0:break
   previous=signature;await asyncio.sleep(.5)
  else:raise StopBatch('Backup not confirmed')
  receipt['backup']={'path':str(path),'signature':signature};write_json(out/'receipt.json',receipt)
  spec=json.loads(args.spec.read_text('utf8'))if args.spec else compile_spec(template)
  write_json(out/'joint_spec.json',spec)
  code=probe(spec).replace('local isolatedTestConfirmed=false','local isolatedTestConfirmed=true -- explicit current-map exception recorded in receipt')
  code=code.replace('local origin=nil -- {x=...,y=...,rotation=...}; choose empty land in the test save','local origin=B.json.decode('+__import__('fullmap_batch').quote(origin)+')')
  (out/'attempt.lua').write_text(code,encoding='utf8')
  receipt['previewAttempted']=True;write_json(out/'receipt.json',receipt)
  try:
   result=await call(pre+code);write_json(out/'result.json',result)
   receipt['outcome']='returned';receipt['errorState']=result.get('errorState');write_json(out/'receipt.json',receipt)
   print(json.dumps({'origin':origin,'backup':name,'errorState':result.get('errorState'),'collisions':result.get('collisions'),'networks':len(result.get('networks',[]))}))
  except BaseException as e:
   receipt['outcome']='error_or_unknown';receipt['error']=str(e);write_json(out/'receipt.json',receipt);raise
if __name__=='__main__':asyncio.run(main())
