local CT=api.type.ComponentType
local out={node=70826,config=B.toPlain(api.engine.getComponent(70826,CT.BASE_NODE_CONFIG)),network=B.toPlain(api.engine.getComponent(70826,CT.TRANSPORT_NETWORK)),edges={}}
local cfg=api.engine.getComponent(70826,CT.BASE_NODE_CONFIG)
if cfg then out.config={connections=B.toPlain(cfg.laneConnections),crosswalks=B.toPlain(cfg.crosswalks)} end
for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(70826)) do
 local e=api.engine.getComponent(id,CT.BASE_EDGE);local tn=api.engine.getComponent(id,CT.TRANSPORT_NETWORK)
 local edges={};for _,v in ipairs(tn.edges) do edges[#edges+1]={modes=B.toPlain(v.transportModes),conns=B.toPlain(v.conns)} end
 out.edges[#out.edges+1]={id=id,node0=e.node0,node1=e.node1,network=edges}
end
return B.json.encode(out)
