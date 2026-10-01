import asyncio
from tf3_mcp.bridge import Bridge

async def main():
    print(await Bridge().call('eval', {'code': 'app.saveGame("tf3_mudanjiang_planks_line_20260930",function() end,false,true);return {requested=true}'}, timeout=15))

asyncio.run(main())
