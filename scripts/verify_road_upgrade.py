"""Validate a road upgrade's structural preview in the live engine, without applying it."""
import asyncio
import json
from pathlib import Path
from tf3_mcp.bridge import Bridge

ROOT = Path(__file__).resolve().parents[1]

async def main():
    bridge = Bridge()
    page = await bridge.call('list_map_entities', {'kind': 'BASE_EDGE', 'limit': 100})
    edge = next(item for item in page['items']
                if '/street/' in item['components']['BASE_EDGE'].get('roadTemplate', '')
                and not item['components']['BASE_EDGE'].get('objects'))
    source = (ROOT / 'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
    old = edge['components']['BASE_EDGE']['roadTemplate']
    target = 'town/town_old_medium' if 'old_medium' not in old else 'town/town_old_small'
    args = {'edge': edge['id'], 'street_type': target, 'preview': True}
    code = ('local env=setmetatable({},{__index=_G}); local s=assert(load('
            + json.dumps(source, ensure_ascii=False) + ',"=upgrade_validation","t",env))(); '
            + 'local args=s._internal.json.decode(' + json.dumps(json.dumps(args)) + '); '
            + 'return s._internal.json.encode(s._internal.commands.upgrade_road(args))')
    result = json.loads(await bridge.call('eval', {'code': code}, engine=True, timeout=30))
    assert result['preview'] and not result['changed']
    assert result['validation'] == 'structural_only' and not result['costAvailable']
    assert result['nodes'] == [edge['components']['BASE_EDGE']['node0'], edge['components']['BASE_EDGE']['node1']]
    output = ROOT / 'road_upgrade_validation.json'
    output.write_text(json.dumps({'isolatedLoad': True, 'request': args, 'result': result}, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
