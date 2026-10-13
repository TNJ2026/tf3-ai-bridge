"""Explicit one-shot recovery CLI. Does not install/enable monitoring."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server/src'))
from tf3_mcp.headless import HeadlessRequests
from tf3_mcp.recovery_adapter import HeadlessRecoveryAdapter
from tf3_mcp.recovery_runtime import RecoveryRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'checkpoint', 'recover-once'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--bridge-dir', type=Path)
    parser.add_argument('--mod-content', type=Path)
    parser.add_argument('--incident')
    parser.add_argument('--allow-launch', action='store_true')
    parser.add_argument('--max-lost-game-time', type=float, default=0)
    parser.add_argument('--max-launches', type=int, default=1)
    parser.add_argument('--allow-unknown-loss', action='store_true',
                        help='Explicitly allow unmeasurable progress loss since the pinned checkpoint')
    args = parser.parse_args()
    if args.action == 'status':
        # Status never constructs a bridge or touches the game/userdata.
        out = RecoveryRuntime(None, args.directory, args.directory).read()
    else:
        if not all((args.config, args.bridge_dir, args.mod_content)):
            parser.error('Live actions require config, bridge-dir and mod-content')
        config = json.loads(args.config.read_text(encoding='utf-8'))
        adapter = HeadlessRecoveryAdapter(HeadlessRequests(args.bridge_dir, args.mod_content),
                                          args.directory, config)
        runtime = RecoveryRuntime(adapter, args.directory, args.bridge_dir)
        if args.action == 'checkpoint':
            out = asyncio.run(runtime.checkpoint())
        else:
            if not args.incident:
                parser.error('recover-once requires an immutable incident ID')
            out = asyncio.run(runtime.recover_once(args.incident, allow_launch=args.allow_launch,
                       max_lost_game_time=args.max_lost_game_time, max_launches=args.max_launches,
                       allow_unknown_loss=args.allow_unknown_loss))
    print(json.dumps(out, ensure_ascii=True, indent=2))
    return 2 if out.get('status') == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
