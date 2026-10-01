local CT=api.type.ComponentType
local x,y=568,-1600
local file='::/industries/forest/forest.con'
assert(api.engine.entityExists(48457) and api.engine.getComponent(48457,CT.TOWN),'town changed')
local near=api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(x,y),280,CT.CONSTRUCTION)
assert(#near==0,'site occupied; inspect before build')
local z=api.engine.terrain.getHeightAt(api.type.Vec2f.new(x,y))
local p=api.type.SimpleProposal.new();local ce=api.type.SimpleProposal.ConstructionEntity.new()
ce.fileName=file;ce.name='牡丹江南郊伐木营地';ce.playerEntity=api.engine.util.getPlayer()
local v=api.type.Vec4f.new
ce.transf=api.type.Mat4f.new(v(-1,0,0,0),v(0,-1,0,0),v(0,0,1,0),v(x,y,z,1))
local modules={};for _,i in ipairs({5,6,7,8,16,18,19,20}) do modules[i]={name='::/industries/forest/field.module',variant=0} end
ce.params={modules=modules,year=1960,productionLevel=0,sizeFactor=0.52983504533768,upgrade=true,seed=38197}
p.constructionsToAdd={ce}
local pd=api.engine.util.proposal.makeProposalData(p,nil)
local out={position={x=x,y=y,z=z},cost=pd.costs,critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),collisions={},built=false}
for _,c in ipairs(pd.collisionInfo.collisionEntities) do out.collisions[#out.collisions+1]=c.entity end
out.buildable=not out.critical and #out.collisions==0
if APPLY then
 assert(out.buildable,'placement preview rejected')
 api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(res,ok) out.built=ok end)
end
return B.json.encode(out)
