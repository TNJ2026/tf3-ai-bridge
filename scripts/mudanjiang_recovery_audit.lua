local CT=api.type.ComponentType;local out={state=B.commands.get_game_state({}),types={},nodes={},industry={}}
for _,k in ipairs(B.json.decode("[\"AIRCRAFT\", \"ANIMAL\", \"ASSET_GROUP\", \"BASE_EDGE\", \"BASE_EDGE_STREET\", \"BASE_NODE\", \"BASE_PARALLEL_STRIP\", \"CUSTOM_STATE\", \"EMISSION_EMITTER\", \"FIELD\", \"GAME_TIME\", \"GAME_SPEED\", \"MODEL_INSTANCE_LIST\", \"NAME\", \"LINE\", \"LOG_BOOK\", \"MODEL_PERSON\", \"MOVE_PATH\", \"MOVE_PATH_AIRCRAFT\", \"STATION\", \"STATION_GROUP\", \"SIM_PERSON\", \"SIM_PERSON_AT_TERMINAL\", \"SIM_PERSON_AT_VEHICLE\", \"SIM_CARGO\", \"SIM_ENTITY_AT_BUILDING\", \"SIM_ENTITY_AT_VEHICLE\", \"SIM_ENTITY_AT_TERMINAL\", \"SIM_ENTITY_IDLE\", \"SIM_ENTITY_MOVING\", \"SIGNAL_LIST\", \"TOWN\", \"INDUSTRY\", \"STOCK_LIST\", \"TOWN_BUILDING\", \"TRANSPORT_VEHICLE\", \"TRAIN\", \"CARRIAGE\", \"CARRIAGE_LIST\", \"VEHICLE_DEPOT\", \"COLOR\", \"BOUNDING_VOLUME\", \"CONSTRUCTION\", \"SUBCONSTRUCTION\", \"PERSON_CAPACITY\", \"PLAYER_OWNED\", \"ACCOUNT\", \"GAME_SCRIPT\", \"WAREHOUSE\", \"TRANSPORT_NETWORK\", \"MAINTENANCE_COST\", \"RAILROAD_CROSSING\", \"PLAYER\", \"WORLD\", \"BRIDGE\", \"BASE_NODE_CONFIG\", \"LAND_VEHICLE\", \"BASE_NODE_TRAFFIC_LIGHT\", \"EDGE_OBJECT\", \"EMISSION_GRID\", \"TERRAIN\", \"SHIP\"]")) do out.types[k]=CT[k] end
for _,n in ipairs({72647,70933,75674,72653,59863,75682}) do
 local row={id=n,exists=api.engine.entityExists(n)}
 if row.exists then
 local c=api.engine.getComponent(n,CT.BASE_NODE);row.base=c~=nil
 if c then row.pos={x=c.position.x,y=c.position.y,z=c.position.z};row.edges=B.toPlain(api.engine.system.streetSystem.getNodeSegments(n));row.components={}
 for k,t in pairs(out.types) do local ok,v=pcall(api.engine.getComponent,n,t);if ok and v~=nil then row.components[#row.components+1]=k end end
 local cfg=api.engine.getComponent(n,CT.BASE_NODE_CONFIG);if cfg then row.laneCount=#cfg.laneConnections end end end
 out.nodes[#out.nodes+1]=row
end
for _,n in ipairs({75918,31520}) do if api.engine.entityExists(n) then local c=api.engine.getComponent(n,CT.INDUSTRY);if c then out.industry[#out.industry+1]={id=n,construction=c.construction} end end end
return B.json.encode(out)