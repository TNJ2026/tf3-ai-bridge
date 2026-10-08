import asyncio,json,time,sys
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 b=Bridge(); assert b.heartbeat()['connected']
 stage=sys.argv[1] if len(sys.argv)>1 else 'before'
 assert stage in ('before','partial')
 name='tf3_'+stage+'_fish_harbor_'+time.strftime('%Y%m%d_%H%M%S')
 result=await b.call('eval',{'code':'app.saveGame('+json.dumps(name)+',function() end,false,true);return {requested=true}'},timeout=15)
 root=b.dir.parent/'save'
 files=[]
 for _ in range(30):
  files=[p for p in b.dir.parent.rglob(name+'.sav') if p.stat().st_size>0]
  if files: break
  await asyncio.sleep(.5)
 out={'name':name,'result':result,'files':[{'path':str(p),'size':p.stat().st_size} for p in files]}
 Path('harbor_checkpoint'+('_partial' if stage=='partial' else '')+'.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(out,ensure_ascii=False))
 assert files,'save not verified'
asyncio.run(main())
