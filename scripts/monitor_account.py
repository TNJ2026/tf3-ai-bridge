"""One account snapshot, without historical business reconciliation or a timer."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from batch_warehouses import write_json
from tf3_mcp.no_gui import NoGuiRequests, workflow_lock
from tf3_mcp.no_gui_client import NoGuiClient
from tf3_mcp.no_gui_workflows import OperationsMonitor


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text('utf-8'))
    directory=Path(os.environ['TF3_MCP_DIR'])
    mod=Path(os.environ.get('TF3_MCP_MOD_DIR', str(directory.parent/'staging_area/tnj_tf3_ai_bridge/content/tf3_mcp_bridge')))
    client=NoGuiClient(NoGuiRequests(directory,mod))
    monitor=OperationsMonitor(client,args.output)
    with workflow_lock(directory):
        result=await monitor.once()
    if result['status']=='completed':
        current=monitor.previous
        if current['state']['player']!=plan['session']['player']:
            raise ValueError('Different player; discard this account sample')
        write_json(args.output/'latest.json',current)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
