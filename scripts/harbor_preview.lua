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
return B.json.encode({position={x=x,y=y,z=z},stations=stations,cost=B.toPlain(pd.costs),critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),collisions=collisions})
