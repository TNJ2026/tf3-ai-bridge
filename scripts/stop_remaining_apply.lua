local CT=api.type.ComponentType
local stops={{60802,6798,'商业中心站'},{60810,60817,'西部工业站'},{61759,62477,'东部工业站'},{60812,60999,'东南住宅站'},{62014,61589,'东北住宅站'}}
local out={}
for _,s in ipairs(stops) do
 local id=nil
 for _,e in ipairs(api.engine.system.streetSystem.getNodeSegments(s[1])) do local b=api.engine.getComponent(e,CT.BASE_EDGE);if b.node0==s[2] or b.node1==s[2] then assert(id==nil,'ambiguous road');id=e end end
 assert(id,'road missing')
 local r=B.commands.build_street_stop({edge=id,two_sided=true,name=s[3],preview=false});r.requestedName=s[3];out[#out+1]=r
 if not r.built then break end
end
return B.json.encode(out)
