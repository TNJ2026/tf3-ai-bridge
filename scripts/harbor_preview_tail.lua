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
