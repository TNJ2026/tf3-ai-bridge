local modules={}
local function add(i,j,f,n)
 local name='::/stations/water/'..n..'.module';local id=api.res.moduleRep.find(name);assert(id>=0,name)
 local d=api.res.moduleRep.get(id)
 modules[1000000*(i+100)+100*(j+100)+f]={name=name,variant=0,metadata=d.metadata,updateScript={fileName=d.updateScript.fileName,params=d.updateScript.params}}
end
add(0,1,50,'pedestrian_entrance');add(-1,1,50,'pedestrian_entrance');add(-1,0,53,'passenger_dock_25_25');add(0,-2,4,'passenger_dock_50_12');add(0,-3,36,'small_pier')
local params={seed=1,year=B.commands.get_game_state({}).date.year,modules=modules}
local x,y,z=1915,-2120,2
local V=api.type.Vec4f.new
local ce=api.type.SimpleProposal.ConstructionEntity.new()
ce.fileName='::/stations/water/harbor_modular.con';ce.params=params
ce.transf=api.type.Mat4f.new(V(1,0,0,0),V(0,1,0,0),V(0,0,1,0),V(x,y,z,1))
ce.playerEntity=api.engine.util.getPlayer();ce.name='牡丹江南岸渔货码头'
local p=api.type.SimpleProposal.new();p.constructionsToAdd={ce}
local pd=api.engine.util.proposal.makeProposalData(p,nil)
local collisions={};for _,c in ipairs(pd.collisionInfo.collisionEntities) do collisions[#collisions+1]={id=c.entity,detail=B.commands.get_entity({id=c.entity})} end
local stations={}
for _,c in ipairs(pd.toAddData) do for _,s in ipairs(c.subconstructionDatas) do if s.station then
 local ts={};for _,t in ipairs(s.station.terminals) do ts[#ts+1]={load=t.cargoLoad,unload=t.cargoUnload,node=B.toPlain(t.vehicleNodeId),modes=B.toPlain(t.transportModes),persons=#t.personNodes} end
 stations[#stations+1]={terminals=ts}
end end end
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
