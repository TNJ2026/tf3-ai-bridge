import asyncio,json,sys
from pathlib import Path
from tf3_mcp.bridge import Bridge
async def main():
 job=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
 source=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
 source=source.replace('if #stale > 0 then proposal.streetProposal.nodeConfigsToRemove = stale end', '-- Junction lanes refreshed separately after construction')
 code='local env=setmetatable({},{__index=_G});local s=assert(load('+json.dumps(source)+',"=cargo_job","t",env))();local job=s._internal.json.decode('+json.dumps(json.dumps(job))+');return s._internal.json.encode(s._internal.commands[job.command](job.args))'
 r=json.loads(await Bridge().call('eval',{'code':code},engine=True,timeout=60));Path(sys.argv[2]).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False))
asyncio.run(main())
