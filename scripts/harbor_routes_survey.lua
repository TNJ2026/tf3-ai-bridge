local CT=api.type.ComponentType
local out={stations={},truckPaths={},shipPaths={}}
local ids={79847,106244,106358,56180,56174,62454,62443,62396,61440}
for _,id in ipairs(ids) do local c=api.engine.getComponent(id,CT.STATION);local ts={}
 for i,t in ipairs(c.terminals) do ts[#ts+1]={index=i-1,load=t.cargoLoad,unload=t.cargoUnload,node={entity=t.vehicleNodeId.entity,index=t.vehicleNodeId.index},persons=(function() local a={};for _,n in ipairs(t.personNodes) do a[#a+1]={entity=n.entity,index=n.index} end;return a end)()} end
 out.stations[#out.stations+1]={id=id,terminals=ts,catchables=B.toPlain(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true))}
end
local function path(a,b,mode)
 local p=api.engine.util.pathfinding.findPathNodeToNode({a},{b},{mode});local len=0;local es={}
 for _,s in ipairs(p) do es[#es+1]=s[1].entity;len=len+api.engine.getComponent(s[1].entity,CT.TRANSPORT_NETWORK).edges[s[1].index+1].geometry.length end
 return {steps=#p,length=len,entities=es}
end
local src=api.engine.getComponent(106358,CT.STATION).terminals[1].vehicleNodeId
for _,id in ipairs({56180,56174,62454,62443,62396,61440}) do local n=api.engine.getComponent(id,CT.STATION).terminals[1].vehicleNodeId;out.truckPaths[#out.truckPaths+1]={id=id,outward=path(src,n,api.type.enum.TransportMode.TRUCK),back=path(n,src,api.type.enum.TransportMode.TRUCK)} end
return B.json.encode(out)
