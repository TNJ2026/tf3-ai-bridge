"""Build a clean mod.io package with the native userdata receiver enabled.

Does not install, upload, modify a running mod, or bundle local MCP configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from check_mod_package import check_package
from validate_bridge_compile import check_bridge_compile

RELEASE_FILES = (
    'mod.json', '_metadata/modinfo.json', '_metadata/0.png',
    'content/tf3_mcp_bridge/bridge.gs.lua',
    'content/tf3_mcp_bridge/bridge.script.lua',
    'content/tf3_mcp_bridge/gui/coordinates.script.lua',
    'content/tf3_mcp_bridge/gui/coordinates.res.lua',
    'content/tf3_mcp_bridge/gui/coordinates.css.lua',
)
SCRIPT = 'content/tf3_mcp_bridge/bridge.script.lua'


def build_package(source: Path, output: Path):
    source, output = source.resolve(), output.resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Release output must be separate from the source directory')
    files = {}
    for name in RELEASE_FILES:
        path = source / name
        if path.resolve() != path.absolute() or not path.is_file():
            raise ValueError('Missing or linked release source: ' + name)
        files[name] = path.read_bytes()
    text = files[SCRIPT].decode('utf-8')
    # Content-derived release identity: stable when packaging the same inputs,
    # different after any bundled source or metadata change. Session IDs remain
    # independent; this is not a machine-specific installation identity.
    digest = hashlib.sha256(b'tf3-modio-userdata-v1\0')
    for name, data in sorted(files.items()):
        digest.update(name.encode() + b'\0' + hashlib.sha256(data).digest())
    generation = digest.hexdigest()[:32]
    replacements = {
        'local NO_GUI_GENERATION = "disabled"': f'local NO_GUI_GENERATION = "{generation}"',
        'local NO_GUI_ON_DEMAND = false': 'local NO_GUI_ON_DEMAND = true',
        'local NO_GUI_USERDATA = false': 'local NO_GUI_USERDATA = true',
    }
    for before, after in replacements.items():
        if text.count(before) != 1:
            raise ValueError('Expected unconfigured release source: ' + before)
        text = text.replace(before, after, 1)
    compiled = check_bridge_compile(text)
    files[SCRIPT] = text.encode('utf-8')
    # A fresh output directory prevents overwriting a previous release or
    # accidentally including diagnostic/request files from an installed mod.
    output.mkdir(parents=True, exist_ok=False)
    root = output / 'tnj_tf3_ai_bridge'
    for name, data in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    checked = check_package(root, require_receiver=True)
    if not checked['passed']:
        raise ValueError(checked['problems'])
    archive = output / 'tnj_tf3_ai_bridge.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, data)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert set(bundle.namelist()) == set(files)
        assert all(bundle.read(name) == data for name, data in files.items())
    report = dict(generation=generation, mode='userdata', enabled=True,
                  modRoot=str(root), archive=str(archive),
                  archiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                  files={name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
                  compile=compiled, packageCheck=checked,
                  uploaded=False, installed=False, nativePackageValidation=False)
    (output / 'release.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'mod/tf3_mcp_bridge')
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing outputs are never overwritten')
    args = parser.parse_args()
    print(json.dumps(build_package(args.source, args.output), ensure_ascii=False, indent=2))
