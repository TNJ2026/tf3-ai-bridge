"""Check (default) or atomically regenerate the Lua world-action catalog."""
from pathlib import Path
import argparse
import json
import os
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server/src'))
from tf3_mcp.world_commands import CATALOG


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    path=ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/world_actions.lua'
    source=path.read_text(encoding='utf-8')
    catalog={k:{a:b for a,b in v.items() if b is not None}for k,v in CATALOG.items()}
    result,count=re.subn(r'(?<=\[==\[).*?(?=\]==\])',lambda _:json.dumps(catalog,separators=(',',':')),source,count=1,flags=re.S)
    if count!=1:raise SystemExit('Expected one catalog marker')
    if result!=source:
        if not args.write:raise SystemExit('Lua catalog differs; run with --write')
        temp=path.with_suffix('.tmp')
        temp.write_text(result,encoding='utf-8');os.replace(temp,path)
    print(f'World catalog matches: {len(catalog)} actions')


if __name__=='__main__':main()
