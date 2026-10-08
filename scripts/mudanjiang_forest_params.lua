local c=api.engine.getComponent(48636,api.type.ComponentType.CONSTRUCTION)
return B.json.encode({fileName=c.fileName,params=B.toPlain(c.params),transf=B.toPlain(c.transf)})
