import copy,math
from fullmap_batch import quote
from hub_joint_prototype import probe
from commit_joint_test import GUARD
def direct_source(base,task,live,*,measured_entrance_depth=None):
 role=task["kind"]
 f=copy.deepcopy(next(f for f in base['facilities'] if f['role']==role));angle=math.radians(task['rotation']);depth=35 if role=='road_depot' else 30
 if measured_entrance_depth is not None:
  assert isinstance(measured_entrance_depth,(int,float)) and math.isfinite(measured_entrance_depth) and 0<measured_entrance_depth<200,'Invalid measured entrance depth'
  depth=measured_entrance_depth
 target={'x':task['position']['x']+depth*math.sin(angle),'y':task['position']['y']-depth*math.cos(angle)}
 choices=[]
 for n in live['nodes']:
  es=[e for e in live['edges'] if n['entity'] in (e['node0'],e['node1'])]
  if len(es)==2:choices.append((math.hypot(n['position']['x']-target['x'],n['position']['y']-target['y']),n,es))
 distance,node,es=min(choices,key=lambda x:x[0]);assert distance<.2,'Native main-road junction changed'
 anchor=node['position'];f.update(localPosition={'x':anchor['x']-depth*math.sin(angle),'y':anchor['y']+depth*math.cos(angle),'z':0},relativeRotation=task['rotation'])
 spec=copy.deepcopy(base);roads=[];existing={}
 for i,e in enumerate(es):
  r=copy.deepcopy(e);r.update(entity=-3-i,buildPhase='frontage')
  for k in (0,1):
   nid=r['node'+str(k)]
   if nid==node['entity']:r['node'+str(k)]=-2
   else:existing[nid]=r['position'+str(k)]
  roads.append(r)
 binding={'roadNode':-2}
 if role=='road_depot':binding['expectedLocalPort']=anchor
 spec.update(facilities=[f],nodes=[{'entity':-2,'position':anchor}],roads=roads,portBindings={role:binding},bindGeneratedPorts=True,alignGeneratedPortGeometry=True,requireWalkingPreview=False)
 code=probe(spec).replace('local isolatedTestConfirmed=false','local isolatedTestConfirmed=true').replace('local origin=nil -- {x=...,y=...,rotation=...}; choose empty land in the test save','local origin={x=0,y=0,rotation=0}')
 code=code.replace('for _,row in ipairs(spec.roads)do','for id,p in pairs(B.json.decode('+quote(existing)+'))do positions[tonumber(id)]=p end\nfor _,row in ipairs(spec.roads)do',1)
 code=code.replace('local context=api.type.Context.new();','proposal.streetProposal.edgesToRemove=B.json.decode('+quote([e['id'] for e in es])+');proposal.streetProposal.nodesToRemove={'+str(node['entity'])+'}\nlocal context=api.type.Context.new();')
 # Existing automatic node configurations contain references to removed edges.
 # Remove configurations at every affected endpoint so native proposal rebuilds them.
 endpoints=sorted({e['node'+str(k)] for e in es for k in (0,1)})
 replacements={e['id']:roads[i]['entity'] for i,e in enumerate(es)}
 configfix="""local configRemove,configAdd={},{};local replacements=B.json.decode("""+quote(replacements)+""");local function mapEdge(id)return replacements[tostring(id)]or id end
 for _,id in ipairs(B.json.decode("""+quote(endpoints)+"""))do
  local cfg=api.engine.getComponent(id,api.type.ComponentType.BASE_NODE_CONFIG)
  if cfg then
   configRemove[#configRemove+1]=id
   if id~="""+str(node['entity'])+""" then
 local v=api.type.BaseNodeLaneConnectionAndEntity.new();v.entity=id;v.comp=cfg
 local lanes={};for _,old in ipairs(cfg.laneConnections)do local l=api.type.LaneConnection.new();l.segment0=mapEdge(old.segment0);l.segment1=mapEdge(old.segment1);l.lane0=old.lane0;l.lane1=old.lane1;l.withRoad=old.withRoad;l.withTram=old.withTram;lanes[#lanes+1]=l end
 local walks={};for _,edge in ipairs(cfg.crosswalks)do walks[#walks+1]=mapEdge(edge)end
 v.comp.laneConnections=lanes;v.comp.crosswalks=walks;configAdd[#configAdd+1]=v
   else assert(not cfg.userModifiedLaneConnections and not cfg.userModifiedTrafficLightStates,'New junction requires explicit user configuration preservation')end
  end
 end;proposal.streetProposal.nodeConfigsToRemove=configRemove;proposal.streetProposal.nodeConfigsToAdd=configAdd
 """
 code=code.replace('local context=api.type.Context.new();',configfix+'local context=api.type.Context.new();')
 code=code.split('local networks=')[0]+'''local collisions={};for _,v in ipairs(pd.collisionInfo.collisionEntities)do collisions[#collisions+1]=v.entity end
 local diagnostic={critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),infos=B.toPlain(pd.errorState.infos),collisions=collisions,bindings=spec.portBindings}
 if diagnostic.critical or #collisions>0 or #diagnostic.messages>0 or #diagnostic.warnings>0 or #diagnostic.infos>0 then return B.json.encode(diagnostic)end
 '''+GUARD.split('local CT=api.type.ComponentType')[0]+"diagnostic.paths=paths;diagnostic.passed=true;return B.json.encode(diagnostic)"

 return code

CROSSWALK="local C=api.type.ComponentType;local found={};for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(BUS_X,BUS_Y),2,C.CONSTRUCTION))do found[#found+1]=id end;assert(#found==1);local c=api.engine.getComponent(found[1],C.CONSTRUCTION);local frozen={};for _,e in ipairs(c.frozenEdges)do frozen[e]=true end;local node,main=nil,{};for _,e in ipairs(c.frozenEdges)do local edge=api.engine.getComponent(e,C.BASE_EDGE);for _,n in ipairs({edge.node0,edge.node1})do local neighbors=api.engine.system.streetSystem.getNodeSegments(n);if #neighbors==3 then assert(not node);node=n;for _,seg in ipairs(neighbors)do if not frozen[seg]then main[#main+1]=seg end end end end end;assert(node and #main==2)\nlocal cfg=api.engine.getComponent(node,C.BASE_NODE_CONFIG);local selected=nil;local best=math.huge;for _,id in ipairs(main)do local e=api.engine.getComponent(id,C.BASE_EDGE);local n=e.node0==node and e.node1 or e.node0;local p=api.engine.getComponent(n,C.BASE_NODE).position;local d=(p.x-AIR_X)^2+(p.y-AIR_Y)^2;if d<best then best=d;selected=id end end\nlocal walks={};for _,id in ipairs(cfg.crosswalks)do assert(id~=selected,'Already present');walks[#walks+1]=id end;walks[#walks+1]=selected\nlocal replacement=api.type.BaseNodeLaneConnectionAndEntity.new();replacement.entity=node;replacement.comp=cfg;replacement.comp.crosswalks=walks\nlocal p=api.type.SimpleProposal.new();p.streetProposal.nodeConfigsToRemove={node};p.streetProposal.nodeConfigsToAdd={replacement};local pd=api.engine.util.proposal.makeProposalData(p,nil);local out={node=node,crosswalk=selected,critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),infos=B.toPlain(pd.errorState.infos),collisions={}};for _,v in ipairs(pd.collisionInfo.collisionEntities)do out.collisions[#out.collisions+1]=v.entity end\nassert(not out.critical and #out.messages==0 and #out.warnings==0 and #out.infos==0 and #out.collisions==0,'Preview blocked')\n"
