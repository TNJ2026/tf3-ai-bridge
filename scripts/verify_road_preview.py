"""Read-only live road preview smoke test. Never submits a construction command."""
import asyncio
import json
import math
from pathlib import Path
from tf3_mcp.bridge import Bridge

async def main():
    bridge = Bridge()
    page = await bridge.call('list_map_entities', {'kind': 'BASE_EDGE', 'limit': 100})
    edge = next(item['components']['BASE_EDGE'] for item in page['items']
                if item['components']['BASE_EDGE'].get('roadTemplate', '').find('/street/') >= 0)
    p, q = edge['position0'], edge['position1']
    dx, dy = q['x'] - p['x'], q['y'] - p['y']
    length = math.hypot(dx, dy)
    args = {'start': {'node': edge['node0']},
            'end': {'x': p['x'] - dy / length * 80, 'y': p['y'] + dx / length * 80},
            'preview': True, 'max_segment_length': 25, 'snap_radius': 0}
    result = await bridge.call('build_road', args, timeout=30)
    active_updated = 'points' in result
    if not active_updated:
        source = (Path(__file__).resolve().parents[1] / 'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
        code = ('local env=setmetatable({},{__index=_G}); local s=assert(load('
                + json.dumps(source, ensure_ascii=False) + ',"=road_preview_validation","t",env))(); '
                + 'local args=s._internal.json.decode(' + json.dumps(json.dumps(args)) + '); '
                + 'return s._internal.json.encode(s._internal.commands.build_road(args))')
        result = json.loads(await bridge.call('eval', {'code': code}, engine=True, timeout=30))
    assert len(result['points']) == 2
    assert result['points'][0]['node'] == edge['node0']
    assert result['segments'] == 4 and len(result['path']) == 5
    assert isinstance(result['buildable'], bool)
    output = Path(__file__).resolve().parents[1] / 'road_preview_validation.json'
    output.write_text(json.dumps({'activeUpdated': active_updated, 'request': args, 'result': result}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('Read-only live preview verified:', output)

if __name__ == '__main__':
    asyncio.run(main())
