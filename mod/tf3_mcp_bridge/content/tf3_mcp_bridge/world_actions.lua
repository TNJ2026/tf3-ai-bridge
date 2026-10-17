-- Native world action adapter. No eval, arbitrary method lookup from input, or retries.
local M={}
function M.create(d)
 local json=d.json
 local catalog=json.decode([==[{"industry_productivity":{"native":"makeStockListSetModifiersCmd","fields":{"entity":"entity","productivity":"nonnegative"},"component":"INDUSTRY","target":"entity","debug":false},"industry_manual_development":{"native":"makeIndustrySetManualDevelopmentCmd","fields":{"entity":"entity","manual":"bool"},"component":"INDUSTRY","target":"entity","debug":false},"industry_closure_time":{"native":"makeIndustrySetDespawnTimeCmd","fields":{"entity":"entity","timestamp":"integer"},"component":"INDUSTRY","target":"entity","debug":false},"vehicle_manual_departure":{"native":"makeVehicleSetManualDepartureCmd","fields":{"entity":"entity","manual":"bool"},"component":"TRANSPORT_VEHICLE","target":"entity","debug":false},"vehicle_depart":{"native":"makeVehicleTryToDepartCmd","fields":{"entity":"entity"},"component":"TRANSPORT_VEHICLE","target":"entity","debug":false},"vehicle_reverse":{"native":"makeVehicleReverseCmd","fields":{"entity":"entity"},"component":"TRANSPORT_VEHICLE","target":"entity","debug":false},"town_development":{"native":"makeTownSetDevelopmentActiveCmd","fields":{"entity":"entity","active":"bool"},"component":"TOWN","target":"entity","debug":false},"town_initial_capacities":{"native":"makeTownSetInitialLandUseCapacitiesCmd","fields":{"entity":"entity","capacities":"integers3"},"component":"TOWN","target":"entity","debug":false},"town_size":{"native":"makeTownUpdateSizeCmd","fields":{"entity":"entity","factors":"numbers3","update_buildings":"bool"},"component":"TOWN","target":"entity","debug":false},"town_distribution":{"native":"makeTownCustomDistributionWeightsCmd","fields":{"entity":"entity","weights":"weights"},"component":"TOWN","target":"entity","debug":false},"building_protection":{"native":"makeTownBuildingSetBlockedDevelopmentCmd","fields":{"entity":"entity","blocked":"bool"},"component":"TOWN_BUILDING","target":"entity","debug":false},"calendar_speed":{"native":"makeGameSetCalendarSpeedCmd","fields":{"millis_per_day":"positive_integer"},"target":"world","debug":false},"game_date":{"native":"makeGameSetDateCmd","fields":{"year":"year","month":"month","day":"day"},"target":"world","debug":false},"time_of_day":{"native":"makeGameSetTimeOfDayCmd","fields":{"seconds":"day_seconds"},"target":"world","debug":false},"cloud_coverage":{"native":"makeGameSetCloudCoverageCmd","fields":{"coverage":"ratio"},"target":"world","debug":false},"wind":{"native":"makeWorldChangeWindCmd","fields":{"entity":"entity","x":"number","y":"number"},"component":"EMISSION_GRID","target":"entity","debug":false},"entity_emissions":{"native":"makeEntitySetEmissionsCmd","fields":{"entity":"entity","noise_power":"nonnegative","pollution_power":"nonnegative","noise_radius":"nonnegative","pollution_radius":"nonnegative"},"component":"EMISSION_EMITTER","target":"entity","debug":false},"entity_name":{"native":"makeEntitySetNameCmd","fields":{"entity":"entity","name":"text"},"component":"NAME","target":"entity","debug":false},"entity_owner":{"native":"makeEntitySetPlayerCmd","fields":{"entity":"entity","player":"entity"},"component":"PLAYER_OWNED","target":"entity","debug":false},"entity_bulldozable":{"native":"makeWorldSetBulldozableCmd","fields":{"entity":"entity","value":"bool"},"target":"entity","debug":false},"stock_cargo_type":{"native":"makeStockListSetStocksCargoTypeCmd","fields":{"entity":"entity","stock_ids":"ids","cargo":"entity"},"component":"STOCK_LIST","target":"entity","debug":false},"stock_discard":{"native":"makeStockListDiscardCargoCmd","fields":{"entity":"entity","stock_ids":"ids","remaining_time":"nonnegative"},"component":"STOCK_LIST","target":"entity","debug":false},"custom_entity_create":{"native":"makeCustomEntityCreateCmd","fields":{"model":"resource"},"target":"create","debug":false},"custom_entity_destroy":{"native":"makeCustomEntityDestroyCmd","fields":{"entity":"entity"},"component":"CUSTOM_STATE","target":"entity","debug":false},"custom_entity_state":{"native":"makeCustomEntityUpdateStateCmd","fields":{"entity":"entity","state":"json_object"},"component":"CUSTOM_STATE","target":"entity","debug":false},"custom_entity_transform":{"native":"makeCustomEntityUpdateTransformationCmd","fields":{"entity":"entity","columns":"matrix"},"component":"CUSTOM_STATE","target":"entity","debug":false},"animal_spawn":{"native":"makeAnimalSpawnAtCmd","fields":{"model":"resource","x":"number","y":"number","look_x":"number","look_y":"number"},"target":"create","debug":false},"animal_state":{"native":"makeAnimalSetStateCmd","fields":{"entity":"entity","movement_type":"entity","target_elapsed":"nonnegative","invalid_elapsed":"nonnegative","speed":"nonnegative","angular_speed":"number"},"component":"ANIMAL","target":"entity","debug":false},"add_player":{"native":"makeGameAddPlayerCmd","fields":{"name":"text","r":"ratio","g":"ratio","b":"ratio"},"target":"create","debug":false},"town_detect_connections":{"native":"makeTownAutoDetectConnectionsCmd","fields":{"towns":"ids"},"target":"towns","debug":false},"debug_maintenance_cost":{"native":"debug.makeMaintenanceCostUpdateCmd","fields":{"entity":"entity","amount":"nonnegative_integer","reset_accumulated":"bool"},"component":"MAINTENANCE_COST","target":"entity","debug":true},"debug_person_happiness":{"native":"debug.makeSimPersonSetHappiness","fields":{"entity":"entity","happiness":"ratio"},"component":"SIM_PERSON","target":"entity","debug":true},"debug_person_state":{"native":"debug.makeSimPersonSetStateCmd","fields":{"entity":"entity","state":"entity"},"component":"SIM_PERSON","target":"entity","debug":true,"blocked":"Installed API exposes an integer but no validated person-state enum/transition contract; arbitrary states are rejected."},"debug_stock_amount":{"native":"debug.makeStockSetCargoAmountCmd","fields":{"entity":"entity","stock_id":"entity","amount":"nonnegative_integer","cargo":"resource"},"component":"STOCK_LIST","target":"entity","debug":true},"debug_simulation_steps":{"native":"debug.makeGamePerformSimulationStepsCmd","fields":{"steps":"steps"},"target":"world","debug":true},"debug_clear_logbooks":{"native":"debug.makeClearLogbooksCmd","fields":{"towns":"bool"},"target":"world","debug":true},"journal_clear":{"native":"makeJournalClearAllCmd","fields":{},"target":"world","debug":false},"journal_log":{"native":"makeJournalLogEntryCmd","fields":{"entity":"entity","entries":"log_entries"},"target":"entity","debug":false},"industry_extend":{"native":"makeCreateIndustryExtendProposalCmd","fields":{"entity":"entity","try_slots":"slots","keep_slots":"slots"},"component":"CONSTRUCTION","target":"entity","debug":false},"town_create":{"native":"makeTownCreateCmd","fields":{"name":"text","x":"number","y":"number"},"target":"create","debug":false,"blocked":"TownInfo generation has no validated native cost/collision proposal adapter."},"town_destroy":{"native":"makeTownDestroyCmd","fields":{"entity":"entity"},"component":"TOWN","target":"entity","debug":false,"blocked":"Deletes town streets and buildings; affected-entity/collision/removal preview adapter is required."},"town_develop_at":{"native":"makeTownDevelopAtCmd","fields":{"x":"number","y":"number","develop_streets":"bool","upgrade_buildings":"bool"},"target":"world","debug":false,"blocked":"Native developer creates streets/buildings without a validated proposal preview."},"town_connect_industries":{"native":"makeTownConnectWithIndustriesCmd","fields":{"towns":"ids","keep":"bool"},"target":"towns","debug":false,"blocked":"Automatic road generation/removal lacks a validated native quote/collision proposal adapter."},"world_replace_terrain":{"native":"makeWorldReplaceTerrainCmd","fields":{"seed":"text","keep_assets":"bool"},"target":"world","debug":false,"blocked":"Whole-map GameMap/Terrain conversion and affected-entity preview are not validated; never use as a flatten shortcut."},"custom_vehicle":{"native":"makeCustomVehicleCreateOrUpdateCmd","fields":{"source_vehicle":"entity"},"target":"world","debug":false,"blocked":"Custom vehicle MovePathAircraft invariants and depot/flight lifecycle need a validated typed adapter."},"journal_book_asset":{"native":"makeJournalBookAssetCmd","fields":{"entity":"entity"},"target":"entity","debug":false,"blocked":"Installed declaration leaves JournalEntry opaque; no validated constructor/financial semantics."},"debug_component_exchange":{"native":"debug.makeComponentExchangeCmd","fields":{"entity":"entity","source_entity":"entity"},"component":"EMISSION_EMITTER","target":"entity","debug":true}}]==])
 local w={}
 local nativeAccessors={
  ["debug.makeClearLogbooksCmd"]=function()return api.cmd.debug.makeClearLogbooksCmd end,
  ["debug.makeComponentExchangeCmd"]=function()return api.cmd.debug.makeComponentExchangeCmd end,
  ["debug.makeGamePerformSimulationStepsCmd"]=function()return api.cmd.debug.makeGamePerformSimulationStepsCmd end,
  ["debug.makeMaintenanceCostUpdateCmd"]=function()return api.cmd.debug.makeMaintenanceCostUpdateCmd end,
  ["debug.makeSimPersonSetHappiness"]=function()return api.cmd.debug.makeSimPersonSetHappiness end,
  ["debug.makeSimPersonSetStateCmd"]=function()return api.cmd.debug.makeSimPersonSetStateCmd end,
  ["debug.makeStockSetCargoAmountCmd"]=function()return api.cmd.debug.makeStockSetCargoAmountCmd end,
  ["makeAnimalSetStateCmd"]=function()return api.cmd.makeAnimalSetStateCmd end,
  ["makeAnimalSpawnAtCmd"]=function()return api.cmd.makeAnimalSpawnAtCmd end,
  ["makeCreateIndustryExtendProposalCmd"]=function()return api.cmd.makeCreateIndustryExtendProposalCmd end,
  ["makeCustomEntityCreateCmd"]=function()return api.cmd.makeCustomEntityCreateCmd end,
  ["makeCustomEntityDestroyCmd"]=function()return api.cmd.makeCustomEntityDestroyCmd end,
  ["makeCustomEntityUpdateStateCmd"]=function()return api.cmd.makeCustomEntityUpdateStateCmd end,
  ["makeCustomEntityUpdateTransformationCmd"]=function()return api.cmd.makeCustomEntityUpdateTransformationCmd end,
  ["makeCustomVehicleCreateOrUpdateCmd"]=function()return api.cmd.makeCustomVehicleCreateOrUpdateCmd end,
  ["makeEntitySetEmissionsCmd"]=function()return api.cmd.makeEntitySetEmissionsCmd end,
  ["makeEntitySetNameCmd"]=function()return api.cmd.makeEntitySetNameCmd end,
  ["makeEntitySetPlayerCmd"]=function()return api.cmd.makeEntitySetPlayerCmd end,
  ["makeGameAddPlayerCmd"]=function()return api.cmd.makeGameAddPlayerCmd end,
  ["makeGameSetCalendarSpeedCmd"]=function()return api.cmd.makeGameSetCalendarSpeedCmd end,
  ["makeGameSetCloudCoverageCmd"]=function()return api.cmd.makeGameSetCloudCoverageCmd end,
  ["makeGameSetDateCmd"]=function()return api.cmd.makeGameSetDateCmd end,
  ["makeGameSetTimeOfDayCmd"]=function()return api.cmd.makeGameSetTimeOfDayCmd end,
  ["makeIndustrySetDespawnTimeCmd"]=function()return api.cmd.makeIndustrySetDespawnTimeCmd end,
  ["makeIndustrySetManualDevelopmentCmd"]=function()return api.cmd.makeIndustrySetManualDevelopmentCmd end,
  ["makeJournalBookAssetCmd"]=function()return api.cmd.makeJournalBookAssetCmd end,
  ["makeJournalClearAllCmd"]=function()return api.cmd.makeJournalClearAllCmd end,
  ["makeJournalLogEntryCmd"]=function()return api.cmd.makeJournalLogEntryCmd end,
  ["makeStockListDiscardCargoCmd"]=function()return api.cmd.makeStockListDiscardCargoCmd end,
  ["makeStockListSetModifiersCmd"]=function()return api.cmd.makeStockListSetModifiersCmd end,
  ["makeStockListSetStocksCargoTypeCmd"]=function()return api.cmd.makeStockListSetStocksCargoTypeCmd end,
  ["makeTownAutoDetectConnectionsCmd"]=function()return api.cmd.makeTownAutoDetectConnectionsCmd end,
  ["makeTownBuildingSetBlockedDevelopmentCmd"]=function()return api.cmd.makeTownBuildingSetBlockedDevelopmentCmd end,
  ["makeTownConnectWithIndustriesCmd"]=function()return api.cmd.makeTownConnectWithIndustriesCmd end,
  ["makeTownCreateCmd"]=function()return api.cmd.makeTownCreateCmd end,
  ["makeTownCustomDistributionWeightsCmd"]=function()return api.cmd.makeTownCustomDistributionWeightsCmd end,
  ["makeTownDestroyCmd"]=function()return api.cmd.makeTownDestroyCmd end,
  ["makeTownDevelopAtCmd"]=function()return api.cmd.makeTownDevelopAtCmd end,
  ["makeTownSetDevelopmentActiveCmd"]=function()return api.cmd.makeTownSetDevelopmentActiveCmd end,
  ["makeTownSetInitialLandUseCapacitiesCmd"]=function()return api.cmd.makeTownSetInitialLandUseCapacitiesCmd end,
  ["makeTownUpdateSizeCmd"]=function()return api.cmd.makeTownUpdateSizeCmd end,
  ["makeVehicleReverseCmd"]=function()return api.cmd.makeVehicleReverseCmd end,
  ["makeVehicleSetManualDepartureCmd"]=function()return api.cmd.makeVehicleSetManualDepartureCmd end,
  ["makeVehicleTryToDepartCmd"]=function()return api.cmd.makeVehicleTryToDepartCmd end,
  ["makeWorldChangeWindCmd"]=function()return api.cmd.makeWorldChangeWindCmd end,
  ["makeWorldReplaceTerrainCmd"]=function()return api.cmd.makeWorldReplaceTerrainCmd end,
  ["makeWorldSetBulldozableCmd"]=function()return api.cmd.makeWorldSetBulldozableCmd end,
 }
 local function native(spec)
  local getter=nativeAccessors[spec.native]
  if not getter then return nil end
  local ok,value=pcall(getter)
  if ok then return value end
  return nil
 end
 local function finite(v)return type(v)=="number" and v==v and math.abs(v)<math.huge end
 local function array(v,n)
  if type(v)~="table" then return false end
  local count=0;for k in pairs(v)do count=count+1;if type(k)~="number" or k%1~=0 or k<1 or k>#v then return false end end
  return count==#v and (n==nil or count==n)
 end
 local function valid(kind,v)
  if kind=="bool" then return type(v)=="boolean" end
  if kind=="text" or kind=="resource" then
   if type(v)~="string" or #v<1 or #v>256 or v:find("[%z\1-\31]") then return false end
   if kind=="resource" then
    local prefix,path=v:match("^(.-)::/(.+)$")
    if not prefix or (prefix~="" and not prefix:match("^[a-zA-Z0-9_-]+$")) or path:find("\\",1,true) or path:find("//",1,true) or path:sub(-1)=="/" then return false end
    for p in path:gmatch("[^/]+")do if p=="." or p==".." then return false end end
   end
   return true
  end
  if kind=="json_object" then
   local function walk(x,depth)
    if depth>4 then return false end
    if type(x)=="table" then
     local count=0;for k,a in pairs(x)do count=count+1;if count>32 or (type(k)~="string" and (type(k)~="number" or k%1~=0 or k<1 or k>32)) or (type(k)=="string" and (#k<1 or #k>64)) or not walk(a,depth+1) then return false end end
     return true
    end
    return type(x)=="boolean" or type(x)=="string" or finite(x)
   end
   if type(v)~="table" or not walk(v,0) or #json.encode(v)>2048 then return false end
   for k in pairs(v)do if type(k)~="string" then return false end end
   return true
  end
  if kind=="ids" or kind=="integers3" or kind=="numbers3" or kind=="weights" or kind=="matrix" or kind=="log_entries" then
   if not array(v) then return false end
   if kind=="ids" then
    if #v<1 or #v>32 then return false end
    local seen={};for _,x in ipairs(v)do if not valid("entity",x) or seen[x] then return false end;seen[x]=true end
   elseif kind=="integers3" or kind=="numbers3" then
    if #v~=3 then return false end
    for _,x in ipairs(v)do if not valid(kind=="integers3" and "nonnegative_integer" or "nonnegative",x) then return false end end
   elseif kind=="weights" or kind=="matrix" then
    if #v~=(kind=="weights" and 3 or 4) then return false end
    for _,row in ipairs(v)do if not array(row,4) then return false end;for _,x in ipairs(row)do if not valid(kind=="weights" and "nonnegative" or "number",x)then return false end end end
   else
    if #v<1 or #v>16 then return false end
    for _,row in ipairs(v)do if not array(row,3) or not valid("text",row[1]) or not valid("integer",row[2]) or type(row[3])~="boolean" then return false end end
   end
   return true
  end
  local ranges={entity={0,2147483646},integer={-2147483647,2147483646},number={-1e9,1e9},nonnegative={0,1e9},nonnegative_integer={0,2147483646},positive_integer={1,2147483646},ratio={0,1},year={1,9999},month={1,12},day={1,31},day_seconds={0,86399},steps={1,100},slots={1,64}}
  local r=ranges[kind]
  return r and finite(v) and v>=r[1] and v<=r[2] and ((kind=="number" or kind=="nonnegative" or kind=="ratio") or v%1==0)
 end
 function w.validate(cmd,a)
  local allowed={list_world_actions={},preview_world_action={action=true,parameters=true},commit_world_action={preview_token=true,backup_save=true},get_world_action_operation={operation_id=true}}
  local keys=assert(allowed[cmd],"Unknown world command")
  assert(type(a)=="table","Expected arguments")
  for k in pairs(a)do assert(keys[k],"Unexpected argument")end
  for k in pairs(keys)do assert(a[k]~=nil,"Missing argument")end
  if cmd=="preview_world_action" then
   local spec=assert(catalog[a.action],"Unknown action");local p=a.parameters
   assert(type(p)=="table","Expected parameters")
   for k,v in pairs(p)do assert(spec.fields[k] and valid(spec.fields[k],v),"Invalid action parameter: "..tostring(k))end
   for k in pairs(spec.fields)do assert(p[k]~=nil,"Missing action parameter: "..k)end
   if a.action=="game_date" then
    local days={31,28,31,30,31,30,31,31,30,31,30,31}
    if p.year%4==0 and (p.year%100~=0 or p.year%400==0)then days[2]=29 end
    assert(p.day<=days[p.month],"Invalid calendar date")
   end
   if a.action=="custom_entity_transform" then for i=1,4 do assert(p.columns[i][4]==(i==4 and 1 or 0),"Expected affine matrix")end end
   if a.action=="town_distribution" then for _,row in ipairs(p.weights)do assert(row[1]+row[2]+row[3]+row[4]>0,"Zero distribution row")end end
  else
   for _,v in pairs(a)do assert(type(v)=="string" and #v>=1 and #v<=96 and v:match("^[%w_-]+$"),"Invalid token")end
  end
 end
 local fields={INDUSTRY={"stockList","construction","manualDevelopment","closureTimeStamp","level"},TRANSPORT_VEHICLE={"state","autoDeparture","line","depot","userStopped","timeUntilCloseDoors","timeUntilDeparture"},TOWN={"initialLandUseCapacities","sizeFactors","levelToCapacityDistributionWeights","developmentActive"},TOWN_BUILDING={"blockedDevelopment","construction","town"},EMISSION_GRID={"wind","type"},EMISSION_EMITTER={"position","radius","noisePower","pollutionPower"},NAME={"name"},PLAYER_OWNED={"player"},CUSTOM_STATE={"state"},ANIMAL={"movementType","movementSpeed","angularSpeed","targetChangedElapsed","invalidTileElapsed"},MAINTENANCE_COST={"maintenanceCost","accumulatedCost"},SIM_PERSON={"happiness","targetOrAtEntity"},STOCK_LIST={"stocks","modifiers"}}
 local function component(id,kind)
  local value=assert(d.getComponent(id,kind),"Required component unavailable: "..kind)
  return value
 end
 local function snapshot(name,p,allowMissing)
  local s=catalog[name];local out={world=api.engine.util.getWorld(),player=api.engine.util.getPlayer()}
  if s.target=="world" or s.target=="create" then
   -- Engine tickCount advances even while paused; it is not simulation state.
   out.game=d.commands.get_game_state({});out.game.tickCount=nil
   out.cloudCoverage=d.toPlain(d.getComponent(out.world,"WORLD"),0,{"cloudCoverage"})
   if p.model then local id=api.res.modelRep.find(p.model);assert(id and id>=0,"Model resource missing");out.modelId=id end
  elseif s.target=="towns" then
   out.towns={};for _,id in ipairs(p.towns)do out.towns[#out.towns+1]={id=id,data=d.toPlain(component(id,"TOWN"),0,{"initialLandUseCapacities","sizeFactors","developmentActive"})}end
  else
   out.entity=p.entity;out.exists=api.engine.entityExists(p.entity)
   if not out.exists then assert(allowMissing,"Entity no longer exists");return out end
   out.owner=d.ownerOf(p.entity)
   if name=="industry_extend" then
    local c=component(p.entity,"CONSTRUCTION")
    out.construction={fileName=c.fileName,params=d.toPlain(c.params,0)}
   elseif name=="debug_component_exchange" then
    out.source=d.toPlain(component(p.source_entity,"EMISSION_EMITTER"),0,fields.EMISSION_EMITTER)
   end
   if s.component and name~="industry_extend" then
    local selected=fields[s.component]
    if s.component=="STOCK_LIST" then selected={"stocks"}end
    if s.component=="TOWN" then
     local townFields={town_development={"developmentActive"},town_initial_capacities={"initialLandUseCapacities"},town_size={"sizeFactors"},town_distribution={"levelToCapacityDistributionWeights"}}
     selected=townFields[name] or selected
    end
    if s.component=="TOWN" then
     local raw=component(p.entity,s.component);out.component={}
     for _,key in ipairs(selected)do
      local ok,value=pcall(function()return raw[key]end)
      assert(ok and value~=nil,"Town field unavailable: "..key)
      out.component[key]=d.toPlain(value,0)
     end
    else out.component=d.toPlain(component(p.entity,s.component),0,selected,s.component=="STOCK_LIST" and "Engine.Component.StockList" or nil)end
   end
   if name=="industry_productivity" then
    out.stockList=component(p.entity,"INDUSTRY").stockList
    out.productivity=component(out.stockList,"STOCK_LIST").modifiers.productivity
    assert(finite(out.productivity),"Productivity unavailable")
   elseif name=="entity_bulldozable" then out.locked=component(p.entity,"BULLDOZER_INFO").locked
   elseif name=="custom_entity_transform" then
    out.models=d.toPlain(component(p.entity,"MODEL_INSTANCE_LIST"),0,{"fatInstances","thinInstances"},"Engine.Component.ModelInstanceList")
   elseif s.component=="STOCK_LIST" then
    local stocks=component(p.entity,"STOCK_LIST").stocks
    for _,id in ipairs(p.stock_ids or {p.stock_id})do assert(stocks[id+1]~=nil,"Stock slot outside current list")end
   end
  end
  return out
 end
 local function prepare(name,p)
  local spec=catalog[name];assert(d.isCallable(native(spec)),"Native command unavailable")
  assert(d.commands.get_game_state({}).speedup==0,"Pause required")
  local before=snapshot(name,p,false)
  if spec.component=="TRANSPORT_VEHICLE" then assert(before.owner==before.player,"Vehicle not owned by current player")end
  if name=="entity_owner" then component(p.player,"PLAYER")end
  if name=="stock_cargo_type" then assert(api.res.cargoTypeRep.get(p.cargo),"Cargo type missing")end
  if name=="vehicle_depart" then assert(component(p.entity,"TRANSPORT_VEHICLE").state==api.type.enum.TransportVehicleState.AT_TERMINAL,"Vehicle is not waiting at a terminal")end
  if name=="animal_spawn" then
   local model=api.res.modelRep.get(before.modelId);assert(model.metadata.animal,"Model is not an animal")
  end
  if name=="animal_state" then assert(p.movement_type==component(p.entity,"ANIMAL").movementType,"Only current native animal movement type is supported")end
  if name=="debug_stock_amount" then
   local stock=component(p.entity,"STOCK_LIST").stocks[p.stock_id+1]
   assert(p.amount<=stock.capacity,"Requested cargo exceeds native stock capacity")
   local id=api.res.cargoTypeRep.find(p.cargo);assert(id and id>=0,"Cargo resource missing")
  end
  if name=="town_size" then assert(not p.update_buildings,"Immediate building regeneration requires a native construction preview")end
  if name=="industry_extend" then
   assert(p.keep_slots<=p.try_slots,"keep_slots exceeds try_slots")
   local c=component(p.entity,"CONSTRUCTION");local id=api.res.constructionRep.find(c.fileName)
   assert(id and id>=0 and api.res.constructionRep.get(id).isIndustry==true,"Not an industry construction")
  end
  return before
 end
 local function make(name,p,b)
  local fn=native(catalog[name])
  if name=="industry_productivity" then local m=api.type.StockList.Modifiers.new();m.productivity=p.productivity;return fn(p.entity,m) end
  if name=="industry_manual_development" or name=="vehicle_manual_departure" then return fn(p.entity,p.manual)end
  if name=="industry_closure_time" then return fn(p.entity,p.timestamp)end
  if name=="vehicle_depart" or name=="vehicle_reverse" or name=="custom_entity_destroy" then return fn(p.entity)end
  if name=="town_development" then return fn(p.entity,p.active)end
  if name=="town_initial_capacities" then return fn(p.entity,p.capacities)end
  if name=="town_size" then return fn(p.entity,p.factors,p.update_buildings)end
  if name=="town_distribution" then return fn(p.entity,p.weights)end
  if name=="building_protection" then return fn(p.entity,p.blocked)end
  if name=="calendar_speed" then return fn(p.millis_per_day)end
  if name=="game_date" then return fn(api.type.Date.new(p.year,p.month,p.day))end
  if name=="time_of_day" then return fn(p.seconds)end
  if name=="cloud_coverage" then return fn(p.coverage)end
  if name=="wind" then return fn(p.entity,api.type.Vec2f.new(p.x,p.y))end
  if name=="entity_emissions" then return fn(p.entity,p.noise_power,p.pollution_power,p.noise_radius,p.pollution_radius)end
  if name=="entity_name" then return fn(p.entity,p.name,true)end
  if name=="entity_owner" then return fn(p.entity,p.player)end
  if name=="entity_bulldozable" then return fn(p.entity,p.value)end
  if name=="stock_cargo_type" then return fn(p.entity,p.stock_ids,p.cargo)end
  if name=="stock_discard" then return fn(p.entity,p.stock_ids,p.remaining_time)end
  if name=="custom_entity_create" then return fn(b.modelId)end
  if name=="custom_entity_state" then return fn(p.entity,p.state)end
  if name=="custom_entity_transform" then local cols={};for _,v in ipairs(p.columns)do cols[#cols+1]=api.type.Vec4f.new(v[1],v[2],v[3],v[4])end;return fn(p.entity,api.type.Mat4f.new(cols[1],cols[2],cols[3],cols[4]))end
  if name=="animal_spawn" then return fn(p.model,api.type.Vec2f.new(p.x,p.y),api.type.Vec2f.new(p.look_x,p.look_y))end
  if name=="animal_state" then return fn(p.entity,p.movement_type,p.target_elapsed,p.invalid_elapsed,p.speed,p.angular_speed)end
  if name=="add_player" then return fn(p.name,api.type.Vec3f.new(p.r,p.g,p.b))end
  if name=="town_detect_connections" then return fn(p.towns)end
  if name=="debug_maintenance_cost" then return fn(p.entity,p.amount,p.reset_accumulated)end
  if name=="debug_person_happiness" then return fn(p.entity,p.happiness)end
  if name=="debug_person_state" then return fn(p.entity,p.state)end
  if name=="debug_stock_amount" then return fn(p.entity,p.stock_id,p.amount,p.cargo)end
  if name=="debug_simulation_steps" then return fn(p.steps)end
  if name=="debug_clear_logbooks" then return fn(p.towns)end
  if name=="journal_clear" then return fn()end
  if name=="journal_log" then return fn(p.entity,p.entries)end
  if name=="industry_extend" then return fn(p.entity,p.try_slots,p.keep_slots)end
  if name=="debug_component_exchange" then
   local source=component(p.source_entity,"EMISSION_EMITTER")
   local value=api.engine.Component.EmissionEmitter.new()
   value.position=api.type.Vec3f.new(source.position.x,source.position.y,source.position.z)
   value.radius=source.radius;value.noisePower=source.noisePower;value.pollutionPower=source.pollutionPower
   return fn(p.entity,value)
  end
  error("No executable action adapter")
 end
 local function check(op,after)
  local n,p=op.action,op.parameters;local c=after.component or {}
  local function eq(a,b)
   if finite(a) and finite(b)then return math.abs(a-b)<=1e-5*math.max(1,math.abs(a),math.abs(b))end
   if type(a)~="table" or type(b)~="table" then return a==b end
   for k,v in pairs(a)do if not eq(v,b[k])then return false end end
   for k in pairs(b)do if a[k]==nil then return false end end
   return true
  end
  if n=="industry_productivity" then return eq(after.productivity,p.productivity)end
  if n=="industry_manual_development" then return c.manualDevelopment==p.manual end
  if n=="industry_closure_time" then return c.closureTimeStamp==p.timestamp end
  if n=="vehicle_manual_departure" then return c.autoDeparture==not p.manual end
  if n=="town_development" then return c.developmentActive==p.active end
  if n=="town_initial_capacities" then return eq(c.initialLandUseCapacities,p.capacities)end
  if n=="town_size" then return eq(c.sizeFactors,p.factors)end
  if n=="town_distribution" then return eq(c.levelToCapacityDistributionWeights,p.weights)end
  if n=="building_protection" then return c.blockedDevelopment==p.blocked end
  if n=="calendar_speed" then return after.game.millisPerDay==p.millis_per_day end
  if n=="game_date" then return eq(after.game.date,{year=p.year,month=p.month,day=p.day})end
  if n=="time_of_day" then return after.game.timeOfDaySec==p.seconds end
  if n=="cloud_coverage" then return after.cloudCoverage~=nil and eq(after.cloudCoverage.cloudCoverage,p.coverage)end
  if n=="wind" then return c.wind~=nil and eq(c.wind.x,p.x) and eq(c.wind.y,p.y)end
  if n=="entity_name" then return c.name==p.name end
  if n=="entity_owner" then return c.player==p.player end
  if n=="entity_bulldozable" then return after.locked==not p.value end
  if n=="custom_entity_state" then return eq(c.state,p.state)end
  if n=="custom_entity_destroy" then return after.exists==false end
  if n=="debug_maintenance_cost" then return c.maintenanceCost==p.amount end
  if n=="debug_person_happiness" then return eq(c.happiness,p.happiness)end
  if n=="debug_component_exchange" then return eq(c,op.before.source)end
  if n=="stock_cargo_type" then
   for _,id in ipairs(p.stock_ids)do if not c.stocks or not c.stocks[id+1] or c.stocks[id+1].cargoType~=p.cargo then return false end end
   return true
  end
  -- These commands have native completion receipts but no validated complete
  -- effect predicate. Never mislabel a successful callback as verified effect.
  return nil
 end
 function w.workflow(state,root,ledger,req,nativeState)
  ledger.worldActionPreviews=ledger.worldActionPreviews or {};ledger.worldActionOperations=ledger.worldActionOperations or {}
  if req.cmd=="list_world_actions" then
   local result={worldActionsVersion=1,actions={},liveValidated=false}
   for name,s in pairs(catalog)do
    local available=d.isCallable(native(s))
    result.actions[name]={native=s.native,parameters=s.fields,available=available,adapterImplemented=s.blocked==nil,executable=available and s.blocked==nil,blockedReason=s.blocked,debug=s.debug,previewKind="state_change_review_not_native_construction_preview"}
   end
   return result
  end
  if req.cmd=="get_world_action_operation" then
   local op=assert(ledger.worldActionOperations[req.args.operation_id],"Unknown operation")
   assert(op.epoch==req.facilityEpoch,"Operation belongs to another session")
   if op.status=="verified" or op.status=="rejected" or op.status=="accepted_unverified" then return op end
   if op.callback==nil then return op end
   local ok,after=pcall(snapshot,op.action,op.parameters,true)
   if not ok then op.readError=tostring(after);state:set(root);return op end
   op.observed=after
   if op.callback==false then
    if d.signature(after)~=d.signature(op.before) then op.status="rejected_but_state_changed";op.outcomeKnown=false;state:set(root);return op end
    op.status="rejected";op.verified=false;op.outcomeKnown=true
   else
    local matched=check(op,after)
    if catalog[op.action].target=="create" then
     matched=type(op.resultEntity)=="number" and api.engine.entityExists(op.resultEntity)
     op.createdEntityExists=matched
    end
    if matched==false then op.status="readback_mismatch";state:set(root);return op end
    op.verified=matched==true;op.outcomeKnown=true
    op.status=op.verified and "verified" or "accepted_unverified"
    op.verificationScope=op.verified and "declared_static_fields_only" or "native_success_callback_and_independent_snapshot_only_effect_not_verified"
   end
   if ledger.pending==op.request_id then ledger.pending=nil end
   state:set(root);return op
  end
  assert(not ledger.pending and not ledger.pendingWorkflow,"Previous mutation unresolved")
  if req.cmd=="preview_world_action" then
   local name,p=req.args.action,req.args.parameters;local spec=catalog[name]
   if spec.blocked then return {action=name,blocked=true,reason=spec.blocked,native=spec.native,previewKind="capability_only",submitted=false}end
   local before=prepare(name,p);local token=req.id.."_world"
   ledger.worldActionPreviews[token]={action=name,parameters=p,before=before,signature=d.signature(before),epoch=req.facilityEpoch,created=assert(d.wallClock())}
   state:set(root)
   return {preview_token=token,action=name,native=spec.native,before=before,desired=p,debug=spec.debug,previewKind="state_change_review",nativeConstructionPreview=false,requiresBackup=true,expiresInSeconds=60}
  end
  local token=req.args.preview_token;local t=ledger.worldActionPreviews[token]
  ledger.worldActionPreviews[token]=nil;state:set(root)
  assert(t and t.epoch==req.facilityEpoch,"Unknown, consumed or stale preview")
  local age=assert(d.wallClock())-t.created;assert(age>=0 and age<=60,"Preview expired")
  assert(not catalog[t.action].blocked,"Adapter is blocked")
  local before=prepare(t.action,t.parameters);assert(d.signature(before)==t.signature,"Target state changed; preview again")
  local cmd=make(t.action,t.parameters,before)
  local op={operation_id=token,request_id=req.id,epoch=req.facilityEpoch,action=t.action,parameters=t.parameters,before=before,backup_save=req.args.backup_save,status="submitted",verified=false,outcomeKnown=false,doNotResubmit=true}
  ledger.worldActionOperations[token]=op;ledger.pending=req.id;state:set(root)
  local dispatching=true
  local ok,err=pcall(function()
   api.cmd.sendCommand(cmd,function(data,success)
    local current=dispatching and root or (nativeState:get() or {})
    local l=assert(current.uiConstruction,"Action ledger lost")
    local saved=assert(l.worldActionOperations[token],"Action receipt lost")
    if type(success)=="boolean" then saved.callback=success else saved.callbackError="Native callback did not provide boolean success"end
    if data then local good,id=pcall(function()return data.resultEntity end);if good and type(id)=="number" then saved.resultEntity=id end end
    if saved.action=="industry_extend" and success==true then
     local good,proposal=pcall(function()
      local p=assert(data.resultProposal,"Native extension proposal missing")
      return {toAdd=d.toPlain(p.toAdd,0),toRemove=d.toPlain(p.toRemove,0),collidingSubconstructions=d.toPlain(data.resultCollidingSubconstructions,0),applied=false,nativeCostCollisionPreview=false}
     end)
     if good then
      if #json.encode(proposal)<=24000 then saved.proposal=proposal else saved.proposalError="Proposal exceeds return bound; not applied"end
     else saved.proposalError=tostring(proposal)end
    end
    if dispatching then state:set(current)else nativeState:set(current)end
   end)
  end)
  dispatching=false
  if not ok then op.status="unknown";op.dispatchError=tostring(err);state:set(root)end
  return op
 end
 return w
end
return M
