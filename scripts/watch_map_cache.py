"""Keep a revision cache current without construction. Ctrl+C stops polling."""
import argparse
import asyncio
import json
from pathlib import Path
from tf3_mcp.bridge import Bridge
from tf3_mcp.map_cache import MapCache

async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',type=int,required=True)
    parser.add_argument('--end',type=int,required=True)
    parser.add_argument('--hotload',action='store_true')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('map_cache.json'))
    args=parser.parse_args();bridge=Bridge(timeout=60)
    root=Path(__file__).resolve().parents[1]
    async def fetch(request):
        if not args.hotload:return await bridge.call('get_route_snapshot',request,engine=True,timeout=60)
        source=(root/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
        code='local env=setmetatable({},{__index=_G});local s=assert(load('+json.dumps(source)+',"=cache","t",env))();local b=s._internal;return b.json.encode(b.commands.get_route_snapshot(b.json.decode('+json.dumps(json.dumps(request))+')))'
        return json.loads(await bridge.call('eval',{'code':code},engine=True,timeout=60))
    cache=MapCache(fetch,args.output)
    if args.once:
        _,status=await cache.refresh(args.start,args.end,force=True)
        print(json.dumps(status));return
    try:
        print(json.dumps(await cache.start(args.start,args.end)),flush=True)
        while True:
            await asyncio.sleep(15)
            print(json.dumps(cache.status()),flush=True)
    finally:await cache.stop()

if __name__=='__main__':
    try:asyncio.run(main())
    except KeyboardInterrupt:pass
