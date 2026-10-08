import asyncio
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 print(await Bridge().call('eval',{'code':'app.saveGame("tf3_line_retest_after_20260930",function() end,false,true);return {requested=true}'},timeout=15))
asyncio.run(main())


