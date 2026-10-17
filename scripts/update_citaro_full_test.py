"""Apply the user-authorized local Citaro performance profile with backups."""
from pathlib import Path
from datetime import datetime
import json
import re
import shutil
from lupa import LuaRuntime

root = Path(__file__).resolve().parents[1]
source = root / 'mod/tf3_mcp_bridge'
cfg = json.loads((root / '.mcp.json').read_text())['mcpServers']['tf3']['env']
installed = Path(cfg['TF3_MCP_NO_GUI_MOD']).parents[1]
out = root / 'output' / ('citaro_full_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
model = 'content/vehicle/bus/mb_citaro_g1_test/mb_citaro_g1_test.mdl'
bridge = 'content/tf3_mcp_bridge/bridge.script.lua'
paths = [model, bridge, 'mod.json', '_metadata/modinfo.json']
prepared = []
lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute('_ = function(s) return s end')

for label, base in [('source', source), ('installed', installed)]:
    for rel in paths:
        p = base / rel
        backup = out / (label + '_before') / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, backup)
        text = p.read_text(encoding='utf-8')
        if rel == model:
            replacements = {
                'yearFrom = 1997,': 'yearFrom = 1850,',
                'price = -1,': 'price = 1000,',
                'Citaro G1（800 km/h · 10倍装载测试）': 'Citaro G1（800 km/h · 全面强化测试）',
                'score = 40,': 'idle = 0, speed = 0, power = 0,',
                'score = 65,': 'idle = 0, speed = 0, power = 0,',
                'curveSpeedScale = 1,': 'curveSpeedScale = 100,',
                'power = 220,': 'power = 22000,',
                'tractiveEffort = 30,': 'tractiveEffort = 3000,',
                'weightEmpty = 15000,': 'weightEmpty = 1500,',
                'weightMaxPayload = 19800,': 'weightMaxPayload = 1980,\n\t\t\t\tfriction = 0.001,\n\t\t\t\tbrakeDeceleration = 25,',
                'lifespan = 21915,': 'lifespan = 365000,',
                'runningCosts = -1,': 'runningCosts = 100,',
                'comfortFactor = 0.3,': 'comfortFactor = 1,',
                'capacity = 112,': 'capacity = 1120,',
                'loadSpeed = 30,': 'loadSpeed = 300,',
            }
            for old, new in replacements.items():
                assert text.count(old) == 1, (label, old)
                text = text.replace(old, new)
            lua.execute(text)
            m = lua.globals().data()['metadata']
            assert m['landVehicle']['topSpeed'] == 800 / 3.6
            assert m['landVehicle']['engines'][1]['power'] == 22000
            assert m['transportVehicle']['compartments'][1]['loadConfigs'][1]['cargoEntry']['capacity'] == 1120
        elif rel == bridge:
            old = 'local BRIDGE_VERSION = "0.12.36"'
            assert text.count(old) == 1
            text = text.replace(old, 'local BRIDGE_VERSION = "0.12.37"')
            lua.execute('assert(load(...))', text)
        elif rel == 'mod.json':
            data = json.loads(text)
            assert data['revision'] == 12
            data['revision'] = 13
            text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        else:
            data = json.loads(text)
            desc = data['description']
            desc = re.sub(r'更新说明 / Update notes — v[\d.]+（[^）]+）', '更新说明 / Update notes — v0.12.37（2026-10-17）', desc)
            desc = desc.replace('Bridge version: 0.12.36', 'Bridge version: 0.12.37')
            desc += '\n\n更新内容 / Changelog — v0.12.37\n全面强化独立 Citaro 测试车型的动力、装载、容量和经营属性。\nEnhanced the separate Citaro test model with improved performance, loading, capacity and operating properties.'
            data['description'] = desc
            text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        prepared.append((p, text))

assert (source / model).read_bytes() == (installed / model).read_bytes()
for p, text in prepared:
    temp = p.with_name(p.name + '.tmp')
    temp.write_text(text, encoding='utf-8', newline='\n')
    temp.replace(p)
    assert p.read_text(encoding='utf-8') == text
assert (source / model).read_bytes() == (installed / model).read_bytes()
result = {'backup': str(out), 'model': str(installed / model), 'version': '0.12.37', 'revision': 13, 'luaParsed': True, 'sourceInstalledModelMatch': True, 'loaded': False}
(out / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
