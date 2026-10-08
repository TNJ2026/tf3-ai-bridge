import asyncio,json,sys
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 source=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
 args={'x':3750,'y':3600,'tracks':2,'length':160,'rotation':90,'name':'Buxton Cargo','preview':'--apply' not in sys.argv}
 code='local env=setmetatable({},{__index=_G});local s=assert(load('+json.dumps(source)+',"=station_placement","t",env))();return s._internal.json.encode(s._internal.commands.build_rail_station(s._internal.json.decode('+json.dumps(json.dumps(args))+')))'
 r=json.loads(await Bridge().call('eval',{'code':code},engine=True,timeout=60))
 Path('town_cargo_station_'+('preview' if args['preview'] else 'built')+'.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False))
asyncio.run(main())
