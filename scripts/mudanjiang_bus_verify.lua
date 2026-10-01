local CT=api.type.ComponentType;local out={landUse={},mode=api.type.enum.TransportMode.BUS,checks={}}
for _,k in ipairs({'RESIDENTIAL','COMMERCIAL','INDUSTRIAL'}) do out.landUse[k]=api.type.enum.LandUseType[k] end
local mode=api.type.enum.TransportMode.BUS;assert(mode~=nil,'bus mode unavailable')
local nodes={61589,62014,61155,60819,6798,60802,60810,60817,62078,62477,61759,61028,60812,60999,61341}
local function lanes(node)
 local o={};for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(node)) do local t=api.engine.getComponent(id,CT.TRANSPORT_NETWORK);for _,e in ipairs(t.edges) do if e.transportModes[mode] then for _,c in ipairs(e.conns) do if c.entity==node then o[#o+1]=c end end end end end;return o
end
for _,sign in ipairs({1,-1}) do local pass=true;local steps=0;for i=1,#nodes do local j=(i-1+sign)%#nodes+1;local p=api.engine.util.pathfinding.findPathNodeToNode(lanes(nodes[i]),lanes(nodes[j]),{mode});pass=pass and #p>0;steps=steps+#p end;out.checks[#out.checks+1]={direction=sign,allLegsReachable=pass,steps=steps} end
return B.json.encode(out)
