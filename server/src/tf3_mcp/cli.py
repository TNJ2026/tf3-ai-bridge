"""Command-line client for testing the bridge without an MCP host.

    tf3-bridge status
    tf3-bridge ping
    tf3-bridge get_game_state
    tf3-bridge set_game_speed speed=2 expected_speed=0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import server


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def main() -> None:
    parser = argparse.ArgumentParser(prog="tf3-bridge")
    parser.add_argument("cmd", help="'status' or a bridge command name")
    parser.add_argument("args", nargs="*", help="key=value arguments (values parsed as JSON when possible)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="Legacy option; no_gui uses its durable request timeout policy")
    ns = parser.parse_args()

    args = {}
    for item in ns.args:
        key, sep, value = item.partition("=")
        if not sep:
            parser.error(f"argument '{item}' is not key=value")
        args[key] = _parse_value(value)

    try:
        result = asyncio.run(server.bridge_status() if ns.cmd == "status" else server._call(ns.cmd, **args))
    except (server.ToolError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
