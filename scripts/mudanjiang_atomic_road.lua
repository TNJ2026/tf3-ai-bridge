-- Task-specific road proposal. Preview by default; apply only with args.apply=true.
return function(args, bridge)
 local api, CT = api, api.type.ComponentType
 local function vec(p) return api.type.Vec3f.new(p.x,p.y,p.z) end
 local function pos(n) local p=api.engine.getComponent(n,CT.BASE_NODE).position;return {x=p.x,y=p.y,z=p.z} end
 local before={}
 for _,n in ipairs({args.startNode,args.endNode}) do before[n]=api.engine.system.streetSystem.getNodeSegments(n) end
 local pts=args.path
 pts[1]=pos(args.startNode);pts[#pts]=pos(args.endNode)
 local function direction(a,b)
  local x,y,z=b.x-a.x,b.y-a.y,b.z-a.z
  local d=math.sqrt(x*x+y*y)
  return {x=x/d,y=y/d,z=z/d},d
 end
 local directions,lengths={},{}
 for i=1,#pts-1 do directions[i],lengths[i]=direction(pts[i],pts[i+1]) end
 local tangent={}
 tangent[1]=directions[1];tangent[#pts]=directions[#pts-1]
 for i=2,#pts-1 do
  local a,b=directions[i-1],directions[i]
  local x,y=a.x+b.x,a.y+b.y
  local d=math.sqrt(x*x+y*y)
  tangent[i]={x=x/d,y=y/d,z=(a.z+b.z)/2}
 end
 -- Align the new road exactly with the existing terminal stubs.
 for _,v in ipairs({{1,args.startNode,true},{#pts,args.endNode,false}}) do
  local edges=api.engine.system.streetSystem.getNodeSegments(v[2])
  if #edges==1 then
  local e=api.engine.getComponent(edges[1],CT.BASE_EDGE)
  local t=e.node1==v[2] and e.tangent1 or e.tangent0
  local sign=e.node1==v[2] and 1 or -1
  if not v[3] then sign=-sign end
  local d=math.sqrt(t.x*t.x+t.y*t.y)
  tangent[v[1]]={x=t.x/d*sign,y=t.y/d*sign,z=t.z/d*sign}
  end
 end
 local name='::/infrastructure/street/country/country_new_medium.street_template'
 local tpl=api.res.streetTemplateRep.get(api.res.streetTemplateRep.find(name))
 local proposal=api.type.SimpleProposal.new()
 local nodes,edges,ids={},{},{[1]=args.startNode,[#pts]=args.endNode}
 local nextId=-1
 local function id() local n=nextId;nextId=nextId-1;return n end
 for i=2,#pts-1 do
  local n=api.type.NodeAndEntity.new();n.entity=id();n.comp.position=vec(pts[i]);nodes[#nodes+1]=n;ids[i]=n.entity
 end
 for i=1,#pts-1 do
  local e=api.type.SegmentAndEntity.new();e.entity=id();e.type=0
  local c=e.comp;c.node0=ids[i];c.node1=ids[i+1];c.position0=vec(pts[i]);c.position1=vec(pts[i+1])
  local a,b=tangent[i],tangent[i+1];local len=lengths[i]
  c.tangent0=vec({x=a.x*len,y=a.y*len,z=a.z*len});c.tangent1=vec({x=b.x*len,y=b.y*len,z=b.z*len})
  c.type=api.type.enum.BaseEdgeType.NORMAL;c.typeIndex=-1;c.laneConfigs=tpl.laneConfigs
  c.roadTemplate=name;c.roadStyle=tpl.streetStyle;c.roadType=api.type.enum.RoadType.STREET
  edges[#edges+1]=e
 end
 proposal.streetProposal.nodesToAdd=nodes;proposal.streetProposal.edgesToAdd=edges
 -- Configure every new node and each joined node in the same proposal.
 local configs={};local configsRemove={}
 local function appendTurn(list,a,ai,b,bi)
  local l=api.type.LaneConnection.new();l.segment0=a;l.lane0=ai;l.segment1=b;l.lane1=bi;l.withRoad=true;l.withTram=false;list[#list+1]=l
 end
 for i=1,#pts do
  local node=ids[i];local adjacent={};local turns={};local existing={};local hasOldConfig=false
  if node>=0 then
   for _,eid in ipairs(api.engine.system.streetSystem.getNodeSegments(node)) do adjacent[#adjacent+1]={id=eid,comp=api.engine.getComponent(eid,CT.BASE_EDGE)};existing[eid]=true end
   local old=api.engine.getComponent(node,CT.BASE_NODE_CONFIG)
   if old then
    hasOldConfig=true
    assert(not old.userModifiedTrafficLightStates and #old.crosswalks==0,'custom junction requires preservation')
    for _,l in ipairs(old.laneConnections) do appendTurn(turns,l.segment0,l.lane0,l.segment1,l.lane1) end
    configsRemove[#configsRemove+1]=node
   end
  end
  for _,e in ipairs(edges) do if e.comp.node0==node or e.comp.node1==node then adjacent[#adjacent+1]={id=e.entity,comp=e.comp} end end
  for _,a in ipairs(adjacent) do for _,b in ipairs(adjacent) do if a.id~=b.id and not(hasOldConfig and existing[a.id] and existing[b.id]) then
   local na,nb=#a.comp.laneConfigs,#b.comp.laneConfigs
   for ka,la in ipairs(a.comp.laneConfigs) do
    local incoming=(a.comp.node0==node and not la.forward) or (a.comp.node1==node and la.forward)
    if incoming and la.transportModes[api.type.enum.TransportMode.TRUCK] then
     for kb,lb in ipairs(b.comp.laneConfigs) do
      local outgoing=(b.comp.node0==node and lb.forward) or (b.comp.node1==node and not lb.forward)
      if outgoing and lb.transportModes[api.type.enum.TransportMode.TRUCK] then
       appendTurn(turns,a.id,a.comp.node0==node and ka-1 or na-ka,b.id,b.comp.node0==node and kb-1 or nb-kb)
      end
     end
    end
   end
  end end end
  local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=node;v.comp.trafficLightPreference=2;v.comp.laneConnections=turns;configs[#configs+1]=v
 end
 proposal.streetProposal.nodeConfigsToAdd=configs
 proposal.streetProposal.nodeConfigsToRemove=configsRemove
 local pd=api.engine.util.proposal.makeProposalData(proposal,nil)
 local out={segments=#edges,cost=pd.costs,errors={critical=pd.errorState.critical,messages=bridge.toPlain(pd.errorState.messages),warnings=bridge.toPlain(pd.errorState.warnings)},collisions=bridge.toPlain(pd.collisionInfo.collisionEntities),built=false}
 local ignore={[args.startNode]=true,[args.endNode]=true}
 for _,n in ipairs({args.startNode,args.endNode}) do
  for _,e in ipairs(api.engine.system.streetSystem.getNodeSegments(n)) do ignore[e]=true end
 end
 out.blocking={}
 for _,v in ipairs(pd.collisionInfo.collisionEntities) do
  local e=v.entity
  if not ignore[e] and (api.engine.getComponent(e,CT.BASE_EDGE) or api.engine.getComponent(e,CT.BASE_NODE)
   or api.engine.getComponent(e,CT.CONSTRUCTION) or api.engine.getComponent(e,CT.TOWN_BUILDING)) then out.blocking[#out.blocking+1]=e end
 end
 out.buildable=not pd.errorState.critical and #out.blocking==0
 if args.apply then
  assert(out.buildable,'road preview blocked construction')
  api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal,nil,false,true),function(res,success)
   out.built=success

  end)
 end
 out.nodeConfigs=#configs
 return bridge.json.encode(out)
end
