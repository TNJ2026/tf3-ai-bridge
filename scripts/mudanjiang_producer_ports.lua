local CT=api.type.ComponentType;local out={}
for _,id in ipairs({43983,48517,31520,48637,27244}) do
 local ind=api.engine.getComponent(id,CT.INDUSTRY);local c=api.engine.getComponent(ind.construction,CT.CONSTRUCTION);local p=c.transf:getTransl();local row={id=id,construction=ind.construction,water=api.engine.terrain.isOnWater(api.type.Vec2f.new(p.x,p.y)),height=api.engine.terrain.getHeightAt(api.type.Vec2f.new(p.x,p.y)),position={x=p.x,y=p.y,z=p.z},ports={}}
 local frozen={};for _,n in ipairs(c.frozenNodes) do frozen[n]=true end
 for _,e in ipairs(c.frozenEdges) do local edge=api.engine.getComponent(e,CT.BASE_EDGE);for _,n in ipairs({edge.node0,edge.node1}) do if not frozen[n] then local v=api.engine.getComponent(n,CT.BASE_NODE).position;row.ports[#row.ports+1]={node=n,position={x=v.x,y=v.y,z=v.z},edge=e,kind=edge.roadType} end end end
 row.stock=B.commands.get_entity({id=ind.stockList,components={'STOCK_LIST'}})
 out[#out+1]=row
end
return B.json.encode(out)
