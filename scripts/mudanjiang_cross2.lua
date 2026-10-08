local e=api.engine.getComponent(72672,api.type.ComponentType.BASE_EDGE)
return B.json.encode({node0=e.node0,node1=e.node1,p0=B.toPlain(e.position0),p1=B.toPlain(e.position1)})
