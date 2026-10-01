assert(not pd.errorState.critical and #pd.errorState.messages==0 and #pd.collisionInfo.collisionEntities==0,'preview rejected')
local CT=api.type.ComponentType
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(x,y),60,CT.CONSTRUCTION)) do
 local c=api.engine.getComponent(id,CT.CONSTRUCTION);assert(c.fileName~=ce.fileName,'harbor already exists')
end
assert(#stations==1 and #stations[1].terminals==1 and stations[1].terminals[1].load and stations[1].terminals[1].unload,'invalid terminal')
local ok=false
api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(_,success)ok=success end)
local found={}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(x,y),60,CT.CONSTRUCTION)) do
 local c=api.engine.getComponent(id,CT.CONSTRUCTION);if c.fileName==ce.fileName then found[#found+1]=B.commands.get_entity({id=id}) end
end
return B.json.encode({applied=ok,constructions=found,cost=pd.costs,state=B.commands.get_game_state({})})
