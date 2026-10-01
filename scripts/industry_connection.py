import asyncio,json,sys
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 plan=json.loads(Path('industry_connection_plan.json').read_text())
 args={'path':plan['preview']['path'],'startNode':49148,'endNode':87621,'apply':'--apply' in sys.argv}
 source=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
 task=Path('scripts/industry_connection.lua').read_text(encoding='utf-8-sig')
 code='local env=setmetatable({},{__index=_G});local s=assert(load('+json.dumps(source)+',"=bridge","t",env))();local f=assert(load('+json.dumps(task)+',"=connection","t",env))();return f(s._internal.json.decode('+json.dumps(json.dumps(args))+'),s._internal)'
 r=json.loads(await Bridge().call('eval',{'code':code},engine=True,timeout=60))
 Path('industry_connection_'+('built' if args['apply'] else 'smooth_preview')+'.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(r,ensure_ascii=False))
asyncio.run(main())
