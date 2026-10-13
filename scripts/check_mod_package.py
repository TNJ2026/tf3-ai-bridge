"""Offline publication check; never deletes runtime files or changes the game."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Mod root containing mod.json")
    args = parser.parse_args()
    root = args.directory.resolve()
    problems = []
    for name in ("mod.json", "_metadata/modinfo.json"):
        try:
            json.loads((root / name).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            problems.append(f"{name}: {exc}")
    if not (root / "_metadata/0.png").is_file():
        problems.append("Missing cover: _metadata/0.png")
    files = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    runtime = [p for p in files if p.startswith("content/tf3_mcp_bridge/headless/")]
    uppercase = [p for p in files if p != p.lower()]
    if runtime:
        problems.append(f"Runtime request files must not be published: {len(runtime)}")
    if uppercase:
        problems.append(f"Uppercase file paths: {len(uppercase)}")
    print(json.dumps({"directory": str(root), "files": len(files),
                      "problems": problems, "passed": not problems}, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
