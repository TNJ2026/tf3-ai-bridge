local out={paths={},stations={}};local CT=api.type.ComponentType
for _,pair in ipairs({{121498,117999},{117999,121498}}) do local p=api.engine.util.pathfinding.findPathNodeToNode({api.type.NodeId.new(pair[1],0)},{api.type.NodeId.new(pair[2],0)},{api.type.enum.TransportMode.TRAIN});out.paths[#out.paths+1]={from=pair[1],to=pair[2],count=#p} end
for _,id in ipairs({107011,115780}) do local st=api.engine.getComponent(id,CT.STATION);out.stations[#out.stations+1]={id=id,terminals=B.toPlain(st.terminals)} end
return B.json.encode(out)
