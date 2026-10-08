-- Single-proposal HQ diagnostic. No recursive native-object serialization or commit.
local input=B.json.decode(INPUT_JSON)
local phases={}
local function stage(name)
 phases[#phases+1]=name;debugPrint('[tf3_hq_access:'..input.runId..'] '..name)
end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function id(v)assert(finite(v) and v%1==0,'Invalid native entity/index');return v end
local CT=api.type.ComponentType
stage('resolve_road_begin')
local target=nil;local scanned=0
local function same(a,b)return math.abs(a.x-b.x)<.1 and math.abs(a.y-b.y)<.1 and math.abs(a.z-b.z)<.1 end
local roadSeen={}
for _,segments in pairs(api.engine.system.streetSystem.getNode2SegmentMap())do for _,entity in pairs(segments)do if not roadSeen[entity]then
 roadSeen[entity]=true
 scanned=scanned+1;assert(scanned<=20000,'Road scan budget exceeded')
 local e=api.engine.getComponent(entity,CT.BASE_EDGE);local expected=input.road
 if e.roadTemplate==expected.roadTemplate and
  ((same(e.position0,expected.position0)and same(e.position1,expected.position1))or
   (same(e.position0,expected.position1)and same(e.position1,expected.position0)))then
  assert(not target,'Ambiguous current frontage road');target=entity
 end
end end end
assert(target,'Frontage road missing or changed; resurvey instead of reusing IDs')
stage('parameters_begin')
assert(type(B.prepareHeadquarters)=='function','Updated bridge preparation helper required')
local proposal,before,parameters=B.prepareHeadquarters(input.args,stage)
assert(type(parameters)=='table' and type(parameters.modules)=='table' and next(parameters.modules),
 'HQ parameter table missing; no native preview permitted')
assert(finite(parameters.year) and finite(parameters.seed),'Invalid HQ parameters')
stage('parameters_ready')
local context=api.type.Context.new();context.player=before.player;context.checkTerrainAlignment=true
stage('native_preview_begin')
local pd=api.engine.util.proposal.makeProposalData(proposal,context)
stage('native_preview_returned')
local function strings(values)
 local out={};for _,v in ipairs(values)do assert(#out<64,'Error list budget exceeded');out[#out+1]=tostring(v):sub(1,512)end;return out
end
local es=pd.errorState
local check={critical=es.critical,messages=strings(es.messages),infos=strings(es.infos),warnings=strings(es.warnings),collisions={}}
for _,v in ipairs(pd.collisionInfo.collisionEntities)do
 assert(#check.collisions<256,'Collision budget exceeded');check.collisions[#check.collisions+1]=id(v.entity)
end
check.clear=es.critical==false and #check.messages==0 and #check.infos==0 and #check.warnings==0 and #check.collisions==0
local result={previewOnly=true,commitEnabled=false,nativeProposalCalls=1,road=target,check=check,
 networks={},links={},phases=phases,parametersPrepared=true}
if not check.clear then stage('placement_rejected');return B.json.encode(result)end
stage('typed_network_read_begin')
local count,edgeCount=0,0;local seen={}
local function readNetwork(entity,net)
 id(entity);assert(not seen[entity],'Duplicate network');seen[entity]=true
 count=count+1;assert(count<=128,'Network budget exceeded');assert(net,'Missing transport network')
 local row={entity=entity,edges={}}
 for i,e in ipairs(net.edges)do
  edgeCount=edgeCount+1;assert(edgeCount<=4096,'Edge budget exceeded')
  if e.transportModes[0]then
   assert(type(e.forwardOnly)=='boolean','Missing directed lane flag')
   local a,b=e.conns[1],e.conns[2]
   row.edges[#row.edges+1]={index=i-1,from={entity=id(a.entity),index=id(a.index)},
    to={entity=id(b.entity),index=id(b.index)},forwardOnly=e.forwardOnly}
  end
 end
 result.networks[#result.networks+1]=row
end
for entity,net in pairs(pd.entity2tn)do readNetwork(entity,net)end
if not seen[target]then readNetwork(target,api.engine.getComponent(target,CT.TRANSPORT_NETWORK))end
stage('typed_network_read_complete')
stage('typed_link_read_begin')
local function endpoint(p)
 assert(p and p.edgeId and finite(p.param) and p.param>=0 and p.param<=1,'Invalid automatic link endpoint')
 return {entity=id(p.edgeId.entity),index=id(p.edgeId.index),param=p.param}
end
for _,r in ipairs(pd.tpNetLinkProposal.toAdd)do
 assert(#result.links<1024,'Link budget exceeded')
 result.links[#result.links+1]={from=endpoint(r.link.from),to=endpoint(r.link.to)}
end
stage('typed_link_read_complete')
return B.json.encode(result)
