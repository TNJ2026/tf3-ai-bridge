import asyncio,json
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 b=Bridge(timeout=5)
 print(await b.call('set_game_speed',{'speed':1},engine=True))
 try:
  await asyncio.sleep(45)
 finally:
  print(await b.call('set_game_speed',{'speed':0},engine=True))
 r=await b.call('get_game_state',{},engine=True)
 Path('no_vehicle_simulation_result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
 print(r)
asyncio.run(main())


