import asyncio,json,sys
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 source=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
 task=Path(sys.argv[1]).read_text(encoding='utf-8-sig')
 code='local env=setmetatable({},{__index=_G});local s=assert(load('+json.dumps(source)+',"=bridge","t",env))();local B=s._internal;'+task
 r=await Bridge().call('eval',{'code':code},engine=True,timeout=60)
 if isinstance(r,str):
  try:r=json.loads(r)
  except:pass
 Path(sys.argv[2]).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False)[:18000])
asyncio.run(main())
