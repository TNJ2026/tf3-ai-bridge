"""Preview or submit the approved Guizhou HQ using the corrected isolated bridge.

Commit creates a fresh native preview and consumes its token in the same local
Lua instance. No global state, permission overrides or proposal error bypasses.
"""
import asyncio
import json
import sys
from pathlib import Path

from tf3_mcp.bridge import Bridge


async def main():
    action = sys.argv[1]
    if action not in ('preview', 'commit'):
        raise ValueError('preview or commit required')
    source = Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
    # Add read-only diagnostics while retaining every strict removal guard.
    source = source.replace('local ci=pd.collisionInfo', '''local ci=pd.collisionInfo
   check.removalDetails=toPlain({buildingEntities=ci.buildingEntities,removableModules=ci.removableModules,autoRemovalEntity2models=ci.autoRemovalEntity2models})''')
    assert ']====]' not in source
    code = 'local env=setmetatable({},{__index=_G});local s=assert(load([====[' + source + ']====],"=bridge","t",env))();local B=s._internal;\n'
    code += '''
local town
for _,t in ipairs(B.commands.get_map_info({}).towns) do if t.name=="贵州" then town=t end end
assert(town and town.position.x==2724 and town.position.y==5504,"Guizhou map changed")
local ground=B.commands.get_terrain({x=2549,y=5379})
assert(ground.valid and not ground.water,"HQ terrain invalid")
local preview=B.commands.build_headquarters({town=town.id,x=2549,y=5379,z=ground.height,rotation=0,name="贵州总部"})
'''
    if action == 'commit':
        code += '''
if not preview.preview_token then return B.json.encode({submitted=false,preview=preview}) end
local result=B.commands.commit_facility({preview_token=preview.preview_token})
return B.json.encode({preview=preview,result=result})
'''
    else:
        code += 'return B.json.encode(preview)'
    bridge = Bridge()
    assert bridge.heartbeat()['connected'], 'stale heartbeat'
    result = await bridge.call('eval', {'code': code}, engine=True, timeout=30)
    if isinstance(result, str):
        result = json.loads(result)
    path = Path('exports/guizhou_hq_depot_20261002') / ('hq_' + action + '.json')
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = result.get('result', result)
    print(json.dumps({k: summary.get(k) for k in ('preview', 'preview_token', 'built', 'verified', 'entity', 'town', 'check', 'blocked') if k in summary}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
