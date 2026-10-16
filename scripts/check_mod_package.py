"""Offline publication check; never deletes runtime files or changes the game."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def check_package(root: Path, *, require_receiver=False):
    root = root.resolve()
    problems = []
    for name in ("mod.json", "_metadata/modinfo.json"):
        try:
            json.loads((root / name).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            problems.append(f"{name}: {exc}")
    if not (root / "_metadata/0.png").is_file():
        problems.append("Missing cover: _metadata/0.png")
    files = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    runtime = [p for p in files if p.startswith("content/tf3_mcp_bridge/no_gui/")]
    uppercase = [p for p in files if p != p.lower()]
    if runtime:
        problems.append(f"Runtime request files must not be published: {len(runtime)}")
    if uppercase:
        problems.append(f"Uppercase file paths: {len(uppercase)}")
    if require_receiver:
        script = root / 'content/tf3_mcp_bridge/bridge.script.lua'
        text = script.read_text(encoding='utf-8') if script.is_file() else ''
        if not re.search(r'^local NO_GUI_GENERATION = "[0-9a-f]{32}"$', text, re.M):
            problems.append('Release receiver generation is disabled or invalid')
        for setting in ('NO_GUI_ON_DEMAND', 'NO_GUI_USERDATA'):
            if not re.search(r'^local ' + setting + r' = true$', text, re.M):
                problems.append('Release must enable ' + setting)
        for setting in ('ENABLE_FIRST_READ_PROBE', 'ENABLE_RESOURCE_INGRESS_PROBE'):
            if setting in text:
                problems.append('Release must not contain retired experiment: ' + setting)
        forbidden = [p for p in files if 'ingress_probe' in p or 'ingress_first_read' in p
                     or p.endswith(('.tmp', '.sav', '.log')) or p == '.mcp.json']
        if forbidden:
            problems.append('Diagnostic or private runtime files in release: ' + ', '.join(forbidden))
    return {"directory": str(root), "files": len(files), "problems": problems, "passed": not problems}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Mod root containing mod.json")
    parser.add_argument('--require-receiver', action='store_true', help='Require an enabled production userdata receiver')
    args = parser.parse_args()
    result = check_package(args.directory, require_receiver=args.require_receiver)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == "__main__":
    raise SystemExit(main())
