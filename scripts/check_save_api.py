import asyncio
from tf3_mcp.bridge import Bridge
async def main():
 print(await Bridge().call('eval',{'code':'return {appType=type(app),saveType=app and type(app.saveGame) or "missing"}'},timeout=10))
asyncio.run(main())
