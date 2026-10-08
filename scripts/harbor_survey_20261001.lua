local CT=api.type.ComponentType
local out={state=B.commands.get_game_state({}),cargos={},fish={},demand={},stations=B.commands.list_stations({mine_only=false}),lines=B.commands.list_lines({}),nodes={}}
for id,name in pairs(api.res.cargoTypeRep.getAll(true)) do out.cargos[#out.cargos+1]={id=id,name=name} end
for _,id in ipairs({79848,43983}) do
 local ind=api.engine.getComponent(id,CT.INDUSTRY)
 out.fish[#out.fish+1]={industry=B.commands.get_entity({id=id}),stock=B.commands.get_component_collection({id=id,component='STOCK_LIST',field='stocks',limit=100}),construction=B.commands.get_entity({id=ind.construction})}
end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(1916,-2545),1000,CT.BASE_NODE)) do
 local c=api.engine.getComponent(id,CT.BASE_NODE)
 out.nodes[#out.nodes+1]={id=id,pos=B.toPlain(c.position)}
end
return B.json.encode(out)
