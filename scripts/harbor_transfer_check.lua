local map=api.engine.system.catchmentAreaSystem.getStation2stationsAndDistancesMap()
local out={transfer=B.toPlain(map[106244]),reverse=B.toPlain(map[106358]),networks={}}
local CT=api.type.ComponentType
for _,id in ipairs({106244,105349}) do
 local tn=api.engine.getComponent(id,CT.TRANSPORT_NETWORK);if tn then
 local ns={};for i,n in ipairs(tn.nodes) do ns[#ns+1]={index=i-1,pos=B.toPlain(n.pos)} end
 out.networks[#out.networks+1]={entity=id,nodes=ns}
 end
end
return B.json.encode(out)
