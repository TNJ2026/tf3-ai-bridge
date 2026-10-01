local out={}
for _,n in ipairs({75674,72653,72647,70933}) do out[tostring(n)]={edges=B.toPlain(api.engine.system.streetSystem.getNodeSegments(n)),config=B.commands.get_entity({id=n,components={'BASE_NODE_CONFIG','TRANSPORT_NETWORK'}})} end
return B.json.encode(out)
