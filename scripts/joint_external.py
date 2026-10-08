"""Compile external approach roads into the same proposal as the collection."""
import math
from pathlib import Path


def append_external(plan, hub, spec, origin):
    roads = [r for r in plan['roads'] if r['id'].startswith(hub['owner'] + '_') and not r.get('templateRoad')]
    if len(roads) > 1:
        raise ValueError('Multiple approaches need explicit joint design')
    spec['consumedRoadIds'] = [r['id'] for r in plan['roads'] if r['id'].startswith(hub['owner'] + '_')]
    if not roads: return spec
    road = roads[0]
    angle = math.radians(origin['rotation']); cs, sn = math.cos(angle), math.sin(angle)
    def local(p):
        dx, dy = p['x'] - origin['x'], p['y'] - origin['y']
        return dict(x=cs*dx+sn*dy, y=-sn*dx+cs*dy, z=0)
    points = [local(p) for p in road['path']]
    if len(points) < 2: raise ValueError('Approach needs endpoints')
    distance = lambda a,b: math.hypot(a['x']-b['x'], a['y']-b['y'])
    matches = [n for n in spec['nodes'] if distance(n['position'], points[-1]) < .01]
    if len(matches) != 1: raise ValueError('Approach must meet exactly one group node')
    anchor = road.get('from_node_hint')
    if not isinstance(anchor, int) or anchor < 0: raise ValueError('Existing anchor hint required; rebound at runtime')
    spec['existingBaseNodes'] = [dict(entity=anchor, position=points[0])]
    spec['externalAnchor'] = anchor
    spec['scope'] = 'facilities + internal roads + external approach; single proposal'
    ids = {r['entity'] for r in spec['nodes'] + spec['roads']}
    cursor = min(ids | {-1000}) - 1
    def allocate():
        nonlocal cursor
        cursor -= 1
        return cursor
    nodeids = [anchor]
    for i,p in enumerate(points[1:-1]):
        entity = allocate(); spec['nodes'].append(dict(name='EXT'+str(i), entity=entity, position=p)); nodeids.append(entity)
    nodeids.append(matches[0]['entity'])
    for i,(p,q) in enumerate(zip(points, points[1:])):
        length = distance(p,q)
        if length < 2: raise ValueError('Collapsed approach segment')
        tangents=[]
        for j in (i,i+1):
            a,b = (points[j-1],points[j+1]) if 0 < j < len(points)-1 else (p,q)
            norm=distance(a,b)
            if norm < .01: raise ValueError('Reversing approach tangent')
            tangents.append(dict(x=(b['x']-a['x'])*length/norm,y=(b['y']-a['y'])*length/norm,z=0))
        spec['roads'].append(dict(id='EXTERNAL'+str(i), entity=allocate(), node0=nodeids[i], node1=nodeids[i+1],
            position0=p,position1=q,tangent0=tangents[0],tangent1=tangents[1],roadTemplate=road['street_type'],buildPhase='external'))
    return spec


REBIND = '''
for _,row in ipairs(spec.existingBaseNodes or{})do
 local want=point(row.position);local found=nil;local CT=api.type.ComponentType
 for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(want.x,want.y),1,CT.BASE_NODE))do
  local q=api.engine.getComponent(id,CT.BASE_NODE).position
  if (q.x-want.x)^2+(q.y-want.y)^2<.01 and #api.engine.system.streetSystem.getNodeSegments(id)>0 then
   assert(not found,'Ambiguous external node');found=id
  end
 end
 assert(found,'External node missing or moved')
 api.engine.forEachEntityWithComponent(function(id)
  local c=api.engine.getComponent(id,CT.CONSTRUCTION)
  for _,n in ipairs(c.frozenNodes)do assert(n~=found,'Frozen external anchor')end
 end,CT.CONSTRUCTION)
 for _,r in ipairs(spec.roads)do if r.node0==row.entity then r.node0=found end;if r.node1==row.entity then r.node1=found end end
 local q=api.engine.getComponent(found,CT.BASE_NODE).position
 positions[found]={x=q.x,y=q.y,z=q.z};row.entity=found;spec.externalAnchor=found
end
'''

PREVIEW = '''
local airportRoadLinks=0
local roadIds={};for _,r in ipairs(spec.roads)do roadIds[r.entity]=true end
local airIds={};for id,net in pairs(pd.entity2tn)do for _,e in ipairs(net.edges)do if e.transportModes[13]then airIds[id]=true end end end
for _,r in ipairs(pd.tpNetLinkProposal.toAdd)do local a,b=r.link.from.edgeId.entity,r.link.to.edgeId.entity
 if (airIds[a]and roadIds[b])or(airIds[b]and roadIds[a])then airportRoadLinks=airportRoadLinks+1 end
end
local externalPaths=nil
if spec.externalAnchor then
 local station,goal={},{}
 for _,net in pairs(pd.entity2tn)do
  local cargo,truck,car=false,false,false
  for _,e in ipairs(net.edges)do cargo=cargo or e.transportModes[1];truck=truck or e.transportModes[4];car=car or e.transportModes[2]end
  for _,e in ipairs(net.edges)do if e.transportModes[4]then for _,n in ipairs(e.conns)do
   if cargo and truck and not car then station[key(n)]=true end
   if n.entity==spec.externalAnchor then goal[key(n)]=true end
  end end end
 end
 externalPaths={outbound=reachable(station,goal,4),inbound=reachable(goal,station,4)}
 assert(externalPaths.outbound and externalPaths.inbound,'External vehicle path failed')
 for _,f in ipairs(spec.facilities)do if f.role=='heliport'then assert(airportRoadLinks>0,'Airport road link missing')end end
end
'''

READBACK = '''
if expected.externalAnchor then
 local q=expected.externalAnchor;local anchor=nil
 for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(q.x,q.y),1,CT.BASE_NODE))do
  local p=api.engine.getComponent(id,CT.BASE_NODE).position
  if (p.x-q.x)^2+(p.y-q.y)^2<.01 then assert(not anchor,'Ambiguous external readback');anchor=id end
 end
 assert(anchor,'External anchor missing after build')
 local edgeIds={};for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments(anchor))do edgeIds[#edgeIds+1]=id end
 local a=nodes(stations('truck'),4);local b={}
 for _,n in ipairs(nodes(edgeIds,4))do if n.entity==anchor then b[#b+1]=n end end
 out.paths.external={outbound=path(a,b,4),inbound=path(b,a,4)}
end
'''
