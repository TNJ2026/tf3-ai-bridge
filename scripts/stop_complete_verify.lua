local CT=api.type.ComponentType;local out={valid=true,stops=0}
for _,id in ipairs({75140,62321,61160,62140,75984,62232}) do
 local e=api.engine.getComponent(id,CT.BASE_EDGE);local tn=api.engine.getComponent(id,CT.TRANSPORT_NETWORK)
 assert(#e.objects==2,'expected pair')
 for _,ref in ipairs(e.objects) do
  local s=api.engine.getComponent(ref[1],CT.STATION);assert(s and #s.terminals>0,'missing terminal')
  for _,t in ipairs(s.terminals) do assert(t.vehicleNodeId.entity==id and t.vehicleNodeId.index>=0 and t.vehicleNodeId.index<#tn.nodes,'invalid vehicle node');assert(#t.personNodes>0,'no passenger node');for _,n in ipairs(t.personNodes) do assert(n.entity==id and n.index>=0 and n.index<#tn.nodes,'invalid passenger node') end end
  assert(api.engine.system.streetSystem.getEdgeForEdgeObject(ref[1])==id,'bad ownership');out.stops=out.stops+1
 end
end
return B.json.encode(out)
