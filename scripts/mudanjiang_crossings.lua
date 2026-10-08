local out={}
for _,id in ipairs({72667,72668,70978,70977,72774}) do
 local e=api.engine.getComponent(id,api.type.ComponentType.BASE_EDGE)
 out[#out+1]={id=id,node0=e.node0,node1=e.node1,p0=B.toPlain(e.position0),p1=B.toPlain(e.position1)}
end
return B.json.encode(out)
