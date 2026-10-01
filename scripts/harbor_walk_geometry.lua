local CT=api.type.ComponentType;local out={edges={}}
local tn=api.engine.getComponent(105349,CT.TRANSPORT_NETWORK)
for i,e in ipairs(tn.edges) do
 local a=api.engine.util.getEdgeGeometry and nil
 local p0=e.geometry:calcPos(0)[1];local p1=e.geometry:calcPos(1)[1]
 if p0.y>=-2110 or p1.y>=-2110 then out.edges[#out.edges+1]={index=i-1,a={entity=e.conns[1].entity,index=e.conns[1].index},b={entity=e.conns[2].entity,index=e.conns[2].index},p0={x=p0.x,y=p0.y,z=p0.z},p1={x=p1.x,y=p1.y,z=p1.z}} end
end
local m=api.engine.system.catchmentAreaSystem.getStation2stationsAndDistancesMap();out.transfer=B.toPlain(m[106244]);out.reverse=B.toPlain(m[106358])
return B.json.encode(out)
