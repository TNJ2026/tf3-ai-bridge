"""Plan or build one facility beside a selected current road curve.

Default is read-only planning. --build authorizes a split followed by a separate
native facility commit within --budget. An existing log is never overwritten.
"""
import argparse
import asyncio
import json
from pathlib import Path

from tf3_mcp.headless import HeadlessRequests, atomic, workflow_lock
from tf3_mcp.headless_client import HeadlessClient
from tf3_mcp.frontage_planning import RESOURCES
from tf3_mcp.frontage_workflow import RoadsidePlacement


async def run(args):
    if args.output.exists(): raise ValueError('Attempt log already exists; inspect it, never replay')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    log={'stage':'started','requests':[],'buildRequested':args.build}
    def save(): atomic(args.output,json.dumps(log,ensure_ascii=False,indent=2).encode('utf-8'))
    client=HeadlessClient(HeadlessRequests(args.bridge_dir,args.mod_content))
    async def call(cmd,arguments):
        row={'command':cmd,'arguments':arguments};log['requests'].append(row);save()
        def ticket(t):row['ticket']=t;save()
        async with client.lock: result=await client.request(cmd,arguments,on_ticket=ticket)
        row['result']=result;save()
        return result
    with workflow_lock(args.bridge_dir):
        try:
            status=await client.status()
            if status.get('pending') or status.get('loadVerification'):raise ValueError('Pending interface/load verification')
            log['identity']=await client.bind(status['receiver']['session'])
            if log['identity']['mapDigest']!=args.map_digest:raise ValueError('Map identity changed')
            save()
            workflow=RoadsidePlacement(call,args.game_content,log,save)
            plan=await workflow.plan(kind=args.kind,edge=args.edge,size=args.size,param=args.param,
                x=args.x,y=args.y,side=args.side,search=not args.exact)
            if args.build:
                if args.budget is None or args.backup is None:raise ValueError('--build requires --budget and --backup')
                await workflow.build(plan,budget=args.budget,floor=args.cash_floor,backup=args.backup,
                                     allow_unpriced_split=args.allow_unpriced_split)
            else:log['stage']='planned' if plan['selected'] else 'no_candidate'
            save()
            print(json.dumps({'stage':log['stage'],'selected':plan['selected'],'output':str(args.output)},ensure_ascii=False))
        except BaseException as exc:
            log['stoppedAt']=log['stage'];log['stage']='stopped_requires_review';log['error']=repr(exc);save()
            raise


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bridge-dir',type=Path,required=True)
    p.add_argument('--mod-content',type=Path,required=True)
    p.add_argument('--game-content',type=Path,required=True)
    p.add_argument('--map-digest',required=True)
    p.add_argument('--kind',choices=RESOURCES,required=True)
    p.add_argument('--edge',type=int,help='Optional with x/y; otherwise resolve the nearest ordinary road')
    p.add_argument('--size',type=int,choices=(1,2,3),default=1)
    p.add_argument('--param',type=float)
    p.add_argument('--x',type=float);p.add_argument('--y',type=float)
    p.add_argument('--side',choices=('auto','left','right'),default='auto')
    p.add_argument('--exact',action='store_true',help='Do not search neighboring road positions')
    p.add_argument('--build',action='store_true')
    p.add_argument('--allow-unpriced-split',action='store_true',
                   help='Explicitly authorize an unknown-cost road split (e.g. disposable test map); budget cannot be guaranteed')
    p.add_argument('--budget',type=float);p.add_argument('--cash-floor',type=float,default=1500000)
    p.add_argument('--backup');p.add_argument('--output',type=Path,required=True)
    return p


if __name__=='__main__':asyncio.run(run(parser().parse_args()))
