-- Historical read-only failed probe: this runtime requires SimpleProposal, not Proposal. Do not rerun.
-- Read-only native Proposal reconstruction, no commands or removals.
local rows=B.json.decode(TASKJSON);local out={};local resource='::/depots/water/water_depot.con'
local params={seed=1,year=B.commands.get_game_state({}).date.year,modules={}}
local built=api.engine.util.construction.getConstructionResult(resource,0,params)
for _,t in ipairs(rows)do
 local p=api.type.Proposal.new();local c=api.type.Proposal.ConstructionEntity.new()
 c.construction.subconstructions=built.subconstructions
 local a=math.rad(t.rotation);local V=api.type.Vec4f.new
 c.transf=api.type.Mat4f.new(V(math.cos(a),math.sin(a),0,0),V(-math.sin(a),math.cos(a),0,0),V(0,0,1,0),V(t.position.x,t.position.y,2,1));c.playerEntity=api.engine.util.getPlayer();p.toAdd={c}
 local context=api.type.Context.new();context.checkTerrainAlignment=true;context.player=api.engine.util.getPlayer()
 local pd=api.engine.util.proposal.makeProposalData(p,context);local collisions={};for _,v in ipairs(pd.collisionInfo.collisionEntities)do collisions[#collisions+1]=v.entity end
 out[#out+1]={id=t.id,critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),collisions=collisions}
end
return B.json.encode(out)
