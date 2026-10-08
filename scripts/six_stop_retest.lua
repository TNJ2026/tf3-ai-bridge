local CT=api.type.ComponentType
local specs={{62014,61589,'东北住宅站'},{60819,61155,'西北住宅站'},{60802,6798,'商业中心站'},{60810,60817,'西部工业站'},{61759,62477,'东部工业站'},{60812,60999,'东南住宅站'}}
local out={previews={},built={},before=B.commands.get_game_state()}
assert(out.before.speedup==0,'must be paused')
for _,s in ipairs(specs) do
 local id
 for _,e in ipairs(api.engine.system.streetSystem.getNodeSegments(s[1])) do local b=api.engine.getComponent(e,CT.BASE_EDGE);if b.node0==s[2] or b.node1==s[2] then assert(id==nil,'ambiguous road');id=e end end
 assert(id,'original road missing')
 local p=B.commands.build_street_stop({edge=id,two_sided=true,name=s[3],preview=true});p.requestedName=s[3];out.previews[#out.previews+1]=p
 if not p.ok or #p.collisions>0 then out.blocked=true;return B.json.encode(out) end
end
for _,p in ipairs(out.previews) do
 local r=B.commands.build_street_stop({edge=p.edge,two_sided=true,name=p.requestedName,preview=false});r.requestedName=p.requestedName;out.built[#out.built+1]=r
 if not r.built then out.blocked=true;break end
end
out.after=B.commands.get_game_state();out.lines=B.commands.list_lines({});out.vehicles=B.commands.list_vehicles({})
return B.json.encode(out)
