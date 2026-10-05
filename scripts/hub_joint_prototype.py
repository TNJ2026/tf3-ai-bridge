"""Offline joint-proposal test pack. No bridge calls or native submission path."""
import argparse,copy,json,math
from pathlib import Path
from fullmap_batch import quote
from fullmap_workflow import write_json,atomic_write

def compile_spec(template):
    from road_snap_layout import validate_road_snaps
    validate_road_snaps(template)
    roles={f['role'] for f in template['facilities']}
    marine_air=roles in ({'harbor','water_maintenance','helipad','helipad2','warehouse'},{'harbor','water_maintenance','water_depot','helipad','helipad2','warehouse'})
    marine=marine_air or roles=={'harbor','water_maintenance','truck','warehouse'}
    if not marine and roles not in ({'bus','truck','warehouse','heliport'},{'bus','truck','warehouse','heliport','road_depot'},{'bus','truck','warehouse','heliport','road_depot','road_maintenance'},{'helipad','truck','warehouse'},{'helipad','helipad2','truck','warehouse'}) or len(template['facilities'])!=len(roles):
        raise ValueError('Expected city hub or production helipad hub roles')
    for f in template['facilities']:
        if f['role']=='road_maintenance':
            if f['resource']!='::/depots/road/road_maint_station.con' or not f.get('roadSnap'):
                raise ValueError('Road maintenance requires its native resource and roadside snap geometry')
    if marine:
        expected={'harbor':'::/stations/water/harbor_modular.con','water_maintenance':'::/depots/water/water_maint_station.con','warehouse':'::/warehouses/warehouse.con','truck':'::/stations/street/modular_street_station/modular_terminal.con'}
        expected.update(helipad='::/stations/air/helipad.con',helipad2='::/stations/air/helipad.con')
        expected['water_depot']='::/depots/water/water_depot.con'
        for f in template['facilities']:
            if f['resource']!=expected[f['role']]:raise ValueError('Unexpected fish-port resource: '+f['role'])
            policy='water_surface' if f['role'] in ('harbor','water_maintenance','water_depot') else 'terrain'
            if f.get('heightPolicy')!=policy:raise ValueError('Explicit marine/land height policy required')
        if template.get('cargoPolicy')!={'allowed':['fish'],'oil':'helicopter'}:raise ValueError('Fish-only policy required')
    nodes={}
    for road in template['roads']:
        for end in (0,1):
            name=road['node'+str(end)];point=road['position'+str(end)]
            if name in nodes and nodes[name]!=point:raise ValueError('Conflicting road node positions')
            nodes[name]=copy.deepcopy(point)
    if not nodes and not marine_air:raise ValueError('No internal roads')
    if marine_air and template['roads']:raise ValueError('Air fish-port transfer does not use truck roads')
    # Reserve construction IDs -1..-4; no existing world IDs enter the pack.
    first=-len(roles)-1
    ids={name:first-i for i,name in enumerate(sorted(nodes))}
    roads=[]
    for i,road in enumerate(template['roads']):
        row=copy.deepcopy(road)
        for key in ('position0','position1'):row[key].setdefault('z',0)
        delta={k:row['position1'][k]-row['position0'][k] for k in ('x','y','z')}
        if math.hypot(delta['x'],delta['y'])<2:raise ValueError('Degenerate internal road')
        for key in ('tangent0','tangent1'):row.setdefault(key,delta.copy())
        roads.append(dict(row,entity=first-len(nodes)-i,node0=ids[road['node0']],node1=ids[road['node1']]))
    bindings={}
    for role in ('bus','truck','road_depot'):
        if role not in roles:continue
        ports=template.get('rolePortNodes',{}).get(role,[])
        if len(ports)!=1 or ports[0]not in ids:raise ValueError('Missing/ambiguous '+role+' port')
        bindings[role]={'roadNode':ids[ports[0]],'nativeEntranceNode':None,
                        'status':'unresolved; positional coincidence is not a connection'}
        if role=='road_depot':
            f=next(f for f in template['facilities'] if f['role']==role)
            if f['resource']!='::/depots/road/road_depot/road_depot.con':raise ValueError('Unsupported road depot resource')
            # Native road_depot.script.lua lane1 starts at (0,-35), snap/free node 0.
            # Match its CURRENT proposal geometry, never a captured entity ID or the frozen inner end.
            a=math.radians(f['relativeRotation']);p=f['localPosition']
            bindings[role]['expectedLocalPort']={'x':p['x']+35*math.sin(a),'y':p['y']-35*math.cos(a),'z':p.get('z',0)}
    return {'schema':1,'experimental':True,'commitEnabled':False,
            'collectionKind':'fish_port' if marine else 'aviation',
            'cargoPolicy':copy.deepcopy(template.get('cargoPolicy')),
            'transferMode':'helicopter' if marine_air else 'truck',
            'bindGeneratedPorts':bool(bindings),
            'alignGeneratedPortGeometry':bool(bindings),
            'nativeJointPreviewPassed':False,'connectionsVerified':False,
            'facilities':copy.deepcopy(template['facilities']),
            'requiresNativePortRefresh':template.get('requiresNativePortRefresh',False),
            'configuration':copy.deepcopy(template.get('configuration')),
            'nodes':[{'name':n,'entity':ids[n],'position':p}for n,p in sorted(nodes.items())],
            'roads':roads,'portBindings':bindings,
            'scope':'Internal roads only; external public connection requires a separate destination design'}

def adapt_ports(spec, measured):
    """Prepare a diagnostic variant from measured LOCAL ports, never entity guesses.

    Only straight source segments are supported; return a fresh, unverified spec.
    """
    result=copy.deepcopy(spec);byid={n['entity']:n for n in result['nodes']}
    for role,position in measured.items():
        if role not in result['portBindings']:raise ValueError('Unknown role')
        if any(not isinstance(position.get(k),(int,float))or not math.isfinite(position[k])for k in ('x','y','z')):raise ValueError('Finite local XYZ required')
        nid=result['portBindings'][role]['roadNode'];old=byid[nid]['position']
        for edge in result['roads']:
            if nid not in (edge['node0'],edge['node1']):continue
            a,b=edge['position0'],edge['position1'];dx,dy=b['x']-a['x'],b['y']-a['y'];length=math.hypot(dx,dy)
            if length<1:raise ValueError('Degenerate road')
            for key in ('tangent0','tangent1'):
                v=edge[key]
                if abs(dx*v['y']-dy*v['x'])>0.002*length*max(math.hypot(v['x'],v['y']),1):raise ValueError('Curved road needs explicit redesign')
            for k in (0,1):
                if edge['node'+str(k)]==nid:edge['position'+str(k)]=copy.deepcopy(position)
            a,b=edge['position0'],edge['position1']
            if math.hypot(b['x']-a['x'],b['y']-a['y'])<2:raise ValueError('Adaptation collapses road')
            tangent={k:b[k]-a[k]for k in ('x','y','z')}
            edge['tangent0']=tangent.copy();edge['tangent1']=tangent.copy()
        byid[nid]['position']=copy.deepcopy(position)
        result['portBindings'][role].update(geometryAdapted=True,sourceLocalPosition=old,measuredLocalPosition=copy.deepcopy(position))
    result.update(commitEnabled=False,nativeJointPreviewPassed=False,connectionsVerified=False)
    return result

def probe(spec):
    # Intentionally no sendCommand. Even preview must be run only in an isolated save.
    return '''-- EXPERIMENTAL: isolated test save only. Preview can trigger native assertions.
-- Run inside the reviewed rail_eval bridge scope (B); configure test origin first.
local isolatedTestConfirmed=false
local origin=nil -- {x=...,y=...,rotation=...}; choose empty land in the test save
assert(isolatedTestConfirmed and origin,'Isolated save and test origin required')
local spec=B.json.decode(SPEC)
local V3,V4=api.type.Vec3f.new,api.type.Vec4f.new
local angle=math.rad(origin.rotation or 0);local cs,sn=math.cos(angle),math.sin(angle)
local function point(p,policy)
 local x,y=origin.x+cs*p.x-sn*p.y,origin.y+sn*p.x+cs*p.y
 if policy=='water_surface' then
  local terrain=assert(api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.TERRAIN),'Missing terrain water level')
  return {x=x,y=y,z=terrain.waterLevel+2}
 end
 return {x=x,y=y,z=api.engine.terrain.getHeightAt(api.type.Vec2f.new(x,y))}
end
local function tangent(p)return V3(cs*p.x-sn*p.y,sn*p.x+cs*p.y,p.z)end
local proposal=api.type.SimpleProposal.new();local constructions={};local nodes={};local edges={};local positions={}
for _,f in ipairs(spec.facilities)do
 local c=api.type.SimpleProposal.ConstructionEntity.new();local p=point(f.localPosition,f.heightPolicy)
 local modules={};for slot,m in pairs(f.params.modules or{})do local id=assert(tonumber(slot),'Module slot must be numeric');assert(id%1==0,'Module slot must be integral')
 if spec.collectionKind=='fish_port' then
  local rid=api.res.moduleRep.find(m.name);assert(rid>=0,'Missing module '..m.name);local d=api.res.moduleRep.get(rid)
  m={name=m.name,variant=m.variant or 0,metadata=d.metadata,updateScript={fileName=d.updateScript.fileName,params=d.updateScript.params}}
 end;modules[id]=m end;f.params.modules=modules
 if spec.collectionKind=='fish_port' then f.params.year=B.commands.get_game_state({}).date.year end
 local a=angle+math.rad(f.relativeRotation);c.fileName=f.resource;c.params=f.params;c.name='JOINT_TEST '..f.role;c.playerEntity=api.engine.util.getPlayer()
 c.transf=api.type.Mat4f.new(V4(math.cos(a),math.sin(a),0,0),V4(-math.sin(a),math.cos(a),0,0),V4(0,0,1,0),V4(p.x,p.y,p.z,1))
 constructions[#constructions+1]=c
end
for _,row in ipairs(spec.nodes)do local p=point(row.position);positions[row.entity]=p
 local n=api.type.NodeAndEntity.new();n.entity=row.entity;n.comp.position=V3(p.x,p.y,p.z);nodes[#nodes+1]=n
end
for _,row in ipairs(spec.roads)do
 local templateName=row.roadTemplate
 local resource=api.res.streetTemplateRep.find(templateName)
 if resource<0 and not templateName:find('::/',1,true)then
  templateName='::/infrastructure/street/'..templateName..'.street_template';resource=api.res.streetTemplateRep.find(templateName)
 end
 assert(resource>=0,'Road template missing')
 local tpl=api.res.streetTemplateRep.get(resource);local e=api.type.SegmentAndEntity.new();local a,b=positions[row.node0],positions[row.node1]
 e.entity=row.entity;e.type=0;e.comp.node0=row.node0;e.comp.node1=row.node1
 e.comp.position0=V3(a.x,a.y,a.z);e.comp.position1=V3(b.x,b.y,b.z)
 e.comp.tangent0=tangent(row.tangent0);e.comp.tangent1=tangent(row.tangent1)
 e.comp.type=api.type.enum.BaseEdgeType.NORMAL;e.comp.typeIndex=-1
 e.comp.laneConfigs=tpl.laneConfigs;e.comp.roadTemplate=templateName;e.comp.roadStyle=(row.roadStyle and row.roadStyle~='')and row.roadStyle or tpl.streetStyle;e.comp.roadType=api.type.enum.RoadType.STREET
 edges[#edges+1]=e
end
MARINE_CHECK
proposal.constructionsToAdd=constructions;proposal.streetProposal.nodesToAdd=nodes;proposal.streetProposal.edgesToAdd=edges
local context=api.type.Context.new();context.checkTerrainAlignment=true;context.player=api.engine.util.getPlayer()
context.cleanupStreetGraph=spec.cleanupStreetGraph==true
local pd=api.engine.util.proposal.makeProposalData(proposal,context)
PORT_BIND_PROBE
local networks={};for id,net in pairs(pd.entity2tn)do local row={entity=id,edges={}}
 for _,e in ipairs(net.edges)do local a,b=e.conns[1],e.conns[2];local modes={};for k=0,15 do if e.transportModes[k]then modes[#modes+1]=k end end;row.edges[#row.edges+1]={from={entity=a.entity,index=a.index},to={entity=b.entity,index=b.index},modes=modes}end
 networks[#networks+1]=row
end
local collisions={};local waterSurfaceContacts={}
for _,r in ipairs(pd.collisionInfo.collisionEntities)do
 if spec.collectionKind=='fish_port' and r.entity>=0 and api.engine.getComponent(r.entity,api.type.ComponentType.WATER_MESH)then
  waterSurfaceContacts[#waterSurfaceContacts+1]=r.entity
 else collisions[#collisions+1]=r.entity end
end
local links={toAdd={},toRemove={}}
for _,key in ipairs({'toAdd','toRemove'})do for _,r in ipairs(pd.tpNetLinkProposal[key])do
 local row={};for _,field in ipairs({'first','second',0,1,2})do
  local ok,p=pcall(function()local v=r.link[field];return {entity=v.edgeId.entity,index=v.edgeId.index}end)
  if ok then row[tostring(field)]=p end
 end;if next(row)==nil then links._unavailable='Native link pair endpoints could not be decoded' end;links[key][#links[key]+1]=row
end end
return B.json.encode({previewOnly=true,commitEnabled=false,connectionsVerified=false,
 errorState={critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),infos=B.toPlain(pd.errorState.infos),warnings=B.toPlain(pd.errorState.warnings)},collisions=collisions,networks=networks,
 links=links,portBindings=spec.portBindings,waterSurfaceContacts=waterSurfaceContacts})
'''.replace('SPEC',quote(spec)).replace('MARINE_CHECK',
    (Path(__file__).with_name('fish_port_shore_check.lua').read_text('utf8')if spec.get('collectionKind')=='fish_port' else '')).replace('PORT_BIND_PROBE',
    (Path(__file__).with_name('hub_joint_bind_probe.lua').read_text('utf8')if spec.get('bindGeneratedPorts') else ''))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--template',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    spec=compile_spec(json.loads(a.template.read_text('utf8')))
    write_json(a.output/'joint_spec.json',spec);atomic_write(a.output/'isolated_preview.lua',probe(spec))
    print(json.dumps({'facilities':len(spec['facilities']),'roads':len(spec['roads']),'commitEnabled':False}))
if __name__=='__main__':main()
