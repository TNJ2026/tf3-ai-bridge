import asyncio,json
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 source=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf8')
 task=Path('scripts/mudanjiang_atomic_road.lua').read_text(encoding='utf8').replace('country/country_new_medium.street_template','town/town_old_small.street_template')
 args={'startNode':106625,'endNode':70827,'path':[{}, {'x':1890,'y':-2086,'z':2.0},{'x':1860,'y':-2070,'z':2.0},{}],'apply':False}
 code='local env=setmetatable({},{__index=_G});local B=assert(load('+json.dumps(source)+',"=bridge","t",env))()._internal;local f=assert(load('+json.dumps(task)+',"=frontage","t",env))();return f(B.json.decode('+json.dumps(json.dumps(args))+'),B)'
 r=await Bridge().call('eval',{'code':code},engine=True,timeout=60)
 if isinstance(r,str):r=json.loads(r)
 Path('harbor_frontage_curve_preview.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps(r,ensure_ascii=False))
asyncio.run(main())
