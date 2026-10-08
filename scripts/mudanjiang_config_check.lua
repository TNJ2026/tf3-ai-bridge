local out={}
for _,n in ipairs({72647,70933,75674,72653,59863,75682}) do local cfg=api.engine.getComponent(n,api.type.ComponentType.BASE_NODE_CONFIG);out[#out+1]={node=n,edges=B.toPlain(api.engine.system.streetSystem.getNodeSegments(n)),lanes=cfg and B.toPlain(cfg.laneConnections) or nil} end
return B.json.encode(out)
