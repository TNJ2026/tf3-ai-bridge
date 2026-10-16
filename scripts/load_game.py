"""Explicit native save loading through the no_gui bridge; no computer-use."""
import argparse
import asyncio
import json
from pathlib import Path

from tf3_mcp.no_gui import NoGuiRequests
from tf3_mcp.no_gui_client import NoGuiClient


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge-dir', type=Path, required=True)
    parser.add_argument('--mod-content', type=Path, required=True)
    actions = parser.add_subparsers(dest='action', required=True)
    load = actions.add_parser('load')
    load.add_argument('--slot', required=True)
    load.add_argument('--session', required=True)
    verify = actions.add_parser('verify')
    verify.add_argument('--request-id', required=True)
    verify.add_argument('--deployment-evidence', type=Path, help='Explicit pre-load bridge deployment receipt for an interrupted upgrade load')
    args = parser.parse_args()
    client = NoGuiClient(NoGuiRequests(args.bridge_dir, args.mod_content))
    if args.action == 'load':
        result = await client.load_game(args.slot, args.session)
    else:
        result = await client.verify_loaded_game(args.request_id, deployment_evidence=args.deployment_evidence)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
