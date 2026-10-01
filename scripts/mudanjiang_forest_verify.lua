local CT=api.type.ComponentType;local out={constructions={}}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(568,-1600),40,CT.CONSTRUCTION)) do
 local c=api.engine.getComponent(id,CT.CONSTRUCTION)
 if c.fileName=='::/industries/forest/forest.con' then
 local row={id=id,fileName=c.fileName,industries={},ports={}}
 for _,i in ipairs(c.industries) do local ind=api.engine.getComponent(i,CT.INDUSTRY);row.industries[#row.industries+1]={id=i,capacity=api.engine.util.stock.getCargoMaxProductionPerYear(ind.stockList,12),outputs=B.toPlain(api.engine.util.stock.getInputsOutputsFromRules(ind.stockList)[2])} end
 local frozen={};for _,n in ipairs(c.frozenNodes) do frozen[n]=true end
 for _,e in ipairs(c.frozenEdges) do local edge=api.engine.getComponent(e,CT.BASE_EDGE);for _,n in ipairs({edge.node0,edge.node1}) do if not frozen[n] then local pos=api.engine.getComponent(n,CT.BASE_NODE).position;row.ports[#row.ports+1]={node=n,x=pos.x,y=pos.y,z=pos.z,degree=#api.engine.system.streetSystem.getNodeSegments(n)} end end end
 out.constructions[#out.constructions+1]=row
 end
end
return B.json.encode(out)
