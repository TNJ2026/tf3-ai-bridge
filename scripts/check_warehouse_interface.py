"""Read-only native previews of the four planned warehouses using the disk bridge.

Does not update the running mod, commit tokens, save, or change simulation speed.
"""
import asyncio
import json

from batch_warehouses import PLAN, ROOT, Bridge, fingerprint, write_json


async def main():
    bridge = Bridge()
    assert bridge.heartbeat()["connected"], "stale game heartbeat"
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    current = await bridge.call("get_map_info", engine=True)
    assert fingerprint(current) == fingerprint(plan["snapshot"]["map"]), "planning map changed"
    source = (ROOT / "mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua").read_text(encoding="utf-8")
    assert "]====]" not in source
    tasks = [{"name": w["name"], "x": w["position"]["x"], "y": w["position"]["y"],
              "rotation": w["rotation"], "module_count": 4} for w in plan["warehouses"]]
    payload = json.dumps(tasks, ensure_ascii=False)
    assert "]===]" not in payload
    code = 'local env=setmetatable({},{__index=_G});local s=assert(load([====[' + source + ']====],"=bridge","t",env))();local B=s._internal;\n'
    code += 'local tasks=B.json.decode([===[' + payload + ']===]);local out={state=B.commands.get_game_state({}),previews={}};'
    code += '''
for _,task in ipairs(tasks) do
 local ground=B.commands.get_terrain(task)
 assert(ground.valid and ground.water==false,"warehouse terrain invalid")
 task.z=ground.height
 out.previews[#out.previews+1]={name=task.name,input=task,preview=B.commands.build_warehouse(task)}
end
return B.json.encode(out)
'''
    result = await bridge.call("eval", {"code": code}, engine=True, timeout=30)
    if isinstance(result, str):
        result = json.loads(result)
    path = ROOT / "exports/supply_warehouse_20261002/warehouse_interface_preview.json"
    write_json(path, result)
    print(json.dumps({"path": str(path), "previews": [{"name": row["name"],
        "blocked": row["preview"].get("blocked", False), "capacity": row["preview"].get("expected_capacity"),
        "check": row["preview"].get("check")} for row in result["previews"]]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
