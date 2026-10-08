local CT=api.type.ComponentType
local c=api.engine.getComponent(107442,CT.CONSTRUCTION);local frozen={};for _,n in ipairs(c.frozenNodes) do frozen[n]=true end
local port
for _,e in ipairs(c.frozenEdges) do local b=api.engine.getComponent(e,CT.BASE_EDGE);for _,n in ipairs({b.node0,b.node1}) do if not frozen[n] then port=n end end end
assert(port,'no port')
local out={port=port,pos=B.toPlain(api.engine.getComponent(port,CT.BASE_NODE).position)}
out.preview=B.commands.build_road({start={node=port},['end']={node=70827},street_type='town/town_old_small',max_segment_length=50,preview=true})
return B.json.encode(out)
