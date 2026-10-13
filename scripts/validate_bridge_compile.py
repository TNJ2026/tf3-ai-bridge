"""Offline Lua compile preflight; never executes the bridge or contacts the game."""
import argparse
import importlib
import json
from pathlib import Path

RUNTIMES = ('lua51', 'lua52', 'lua53', 'lua54', 'lua55', 'luajit21')
RESERVED_LOCALS = 16


def check_bridge_compile(source):
    # An explicit margin, not a claim about the native loader's exact wrapper.
    prefix = 'local ' + ','.join(f'bridge_loader_reserve_{n}' for n in range(RESERVED_LOCALS)) + '\n'
    rows = []
    for name in RUNTIMES:
        runtime = importlib.import_module('lupa.' + name).LuaRuntime(unpack_returned_tuples=True)
        compile_only = runtime.eval('''function(s)
            local loader = loadstring or load
            local chunk, err = loader(s)
            return chunk ~= nil, err
        end''')
        for margin, text in ((0, source), (RESERVED_LOCALS, prefix + source)):
            ok, error = compile_only(text)
            if not ok:
                raise ValueError(f'{name}, reserved locals {margin}: {error}')
            rows.append({'runtime': name, 'reservedLocals': margin, 'compiled': True})
    return {'status': 'offline_compile_passed', 'executed': False, 'checks': rows,
            'nativeLoaderVerified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', type=Path, default=Path(__file__).resolve().parents[1] /
                        'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua')
    args = parser.parse_args()
    print(json.dumps(check_bridge_compile(args.path.read_text(encoding='utf-8')), indent=2))
