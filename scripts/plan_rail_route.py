"""Plan without building. Use --snapshot to replay a survey with zero game calls."""
import argparse
import asyncio
import json
import time
from pathlib import Path
from tf3_mcp.bridge import Bridge
from tf3_mcp.staged_planner import plan_staged

async def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start',type=int)
    p.add_argument('--end',type=int)
    p.add_argument('--snapshot',type=Path)
    p.add_argument('--output',type=Path,default=Path('route_candidates.json'))
    p.add_argument('--hotload',action='store_true',help='Use local bridge source for a running older mod; read-only eval')
    args=p.parse_args();begin=time.perf_counter()
    if args.snapshot:
        snapshot=json.loads(args.snapshot.read_text(encoding='utf-8'))
    else:
        if args.start is None or args.end is None or args.start==args.end:p.error('two different construction ids are required')
        request=dict(start_construction=args.start,end_construction=args.end)
        if args.hotload:
            root=Path(__file__).resolve().parents[1]
            source=(root/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
            code='local env=setmetatable({},{__index=_G});local s=assert(load('+json.dumps(source)+',"=planner","t",env))();local b=s._internal;return b.json.encode(b.commands.get_route_snapshot(b.json.decode('+json.dumps(json.dumps(request))+')))'
            snapshot=json.loads(await Bridge().call('eval',{'code':code},engine=True,timeout=30))
        else:
            snapshot=await Bridge().call('get_route_snapshot',request,engine=True,timeout=30)
        args.output.with_suffix('.snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False),encoding='utf-8')
    result=plan_staged(snapshot)
    result['stats'].update(bridgeRequests=0 if args.snapshot else 1,totalSeconds=round(time.perf_counter()-begin,4))
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'stats':result['stats'],'candidates':len(result['candidates']),'output':str(args.output.resolve())},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
