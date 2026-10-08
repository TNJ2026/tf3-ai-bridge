"""Read-only live verification using an isolated UTF-8 Lua bridge instance."""
import asyncio
import json
from pathlib import Path

from tf3_mcp.bridge import Bridge


async def main():
    bridge = Bridge()
    assert bridge.heartbeat()["connected"], "game heartbeat is stale"
    source = Path("mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua").read_text(encoding="utf8")
    assert "]====]" not in source
    code = "local env=setmetatable({},{__index=_G});local s=assert(load([====[" + source + "]====], '=bridge','t',env))();local B=s._internal;\n" + r'''
local map=B.commands.get_map_info({})
local town
for _,t in ipairs(map.towns) do if t.name=="奎屯" then town=t end end
assert(town,"current Kuitun town is absent")
local out={state=B.commands.get_game_state({}),town=town,
 catalog=B.commands.list_facility_resources({search="headquarter"}),facilities=B.commands.list_facilities({})}
out.headquarters={}
for _,f in ipairs(out.facilities.items) do
 if f.category=="headquarters" then
  local config=B.commands.get_facility_config({entity=f.entity})
  config.closestTown=api.engine.system.streetConnectorSystem.getConstructionClosestTown(f.entity)
  out.headquarters[#out.headquarters+1]=config
 end
end
local hq=ug_require("::/landmarks/hq/headquarter.script.tl")
out.nativeTemplate=B.toPlain(hq.createTemplateFn({},{}))
local resource="::/landmarks/hq/headquarter.con"
local desc=api.res.constructionRep.get(api.res.constructionRep.find(resource))
local company=ug_require("::/game_mechanics/company/company_util.tl")
local cache=company.getConstructionDisableCacheData({{resource,desc.metadata,"Headquarters"}})
out.nativePermission=B.toPlain(company.getConstructionDisableReason(resource,desc.metadata,cache))
local ok,value=pcall(B.commands.build_headquarters,{town=town.id,x=town.position.x,y=town.position.y,z=1,preview=true})
out.duplicateGuard={ok=ok,result=ok and value or tostring(value)}
return B.json.encode(out)
'''
    result = await bridge.call("eval", {"code": code}, engine=True, timeout=30)
    if isinstance(result, str):
        result = json.loads(result)
    path = Path("exports/map_info/headquarters_interface_check.json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"path": str(path.resolve()), "state": result["state"],
                      "nativeTemplate": result["nativeTemplate"],
                      "nativePermission": result.get("nativePermission"),
                      "duplicateGuard": result["duplicateGuard"],
                      "headquarters": [{k: h.get(k) for k in ("entity", "owner", "position", "closestTown", "cloneable", "configurable")}
                                       for h in result["headquarters"]]}, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(main())
