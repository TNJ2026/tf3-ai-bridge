import asyncio,json,sys
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 args={'start':{'node':25624},'end':{'x':3750,'y':3568},'via':[{'x':3570,'y':3560},{'x':3680,'y':3568}], 'street_type':'town/town_old_small','max_segment_length':40,'preview':'--apply' not in sys.argv}
 source=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
 code='local env=setmetatable({},{__index=_G});local s=assert(load('+json.dumps(source)+',"=station_road","t",env))();return s._internal.json.encode(s._internal.commands.build_road(s._internal.json.decode('+json.dumps(json.dumps(args))+')))'
 r=json.loads(await Bridge().call('eval',{'code':code},engine=True,timeout=60));Path('town_station_road_'+('preview' if args['preview'] else 'built')+'.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False))
asyncio.run(main())
