local CT=api.type.ComponentType
local a=api.engine.getComponent(106244,CT.STATION).terminals[1]
local b=api.engine.getComponent(106358,CT.STATION).terminals[1]
local aa,bb={},{};for _,n in ipairs(a.personNodes) do aa[#aa+1]=n end;for _,n in ipairs(b.personNodes) do bb[#bb+1]=n end
local out={}
for _,mode in ipairs({0,1,12}) do
 local start,finish=aa,bb
 if mode==12 then start={api.engine.getComponent(79847,CT.STATION).terminals[1].vehicleNodeId};finish={a.vehicleNodeId} end
 local p=api.engine.util.pathfinding.findPathNodeToNode(start,finish,{mode});local len=0
 for _,v in ipairs(p) do len=len+api.engine.getComponent(v[1].entity,CT.TRANSPORT_NETWORK).edges[v[1].index+1].geometry.length end
 out[#out+1]={mode=mode,steps=#p,length=len}
end
return B.json.encode(out)
