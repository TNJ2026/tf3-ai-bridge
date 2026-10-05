"""Offline configurable hub layouts. Building sizes are never geometrically scaled."""
import argparse,copy,hashlib,json,math
from pathlib import Path
from fullmap_workflow import write_json,atomic_write
from fullmap_hub_template import diagram
from hub_joint_prototype import compile_spec

def number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Offsets must be finite numbers in metres')
    return value

def configure(template,config):
    if set(config)-{'name','offsets','moduleSlots','frontExtension','outerExtension'}:raise ValueError('Unknown configuration key')
    out=copy.deepcopy(template);roles={f['role']:f for f in out['facilities']}
    offsets=config.get('offsets',{});selection=config.get('moduleSlots',{})
    if (set(offsets)|set(selection))-set(roles):raise ValueError('Unknown facility role')
    if offsets.get('heliport',{})not in ({},{'x':0,'y':0}):raise ValueError('Airport is the anchor; translate the whole collection at placement')
    shifts={}
    for role in roles:
        offset=offsets.get(role,{})
        if set(offset)-{'x','y'}:raise ValueError('Only local XY offsets are supported')
        shifts[role]={k:number(offset.get(k,0))for k in ('x','y')}
    changes=[]
    for role,f in roles.items():
        for k in ('x','y'):f['localPosition'][k]+=shifts[role][k]
        if role in selection:
            slots=selection[role]
            if not isinstance(slots,list)or any(not isinstance(k,str)for k in slots)or len(slots)!=len(set(slots)):raise ValueError('moduleSlots must be a unique list of string slot IDs')
            modules=f['params'].get('modules',{})
            if set(slots)-set(modules):raise ValueError('Unobserved module slot; requires a fresh native expansion design')
            kept={k:v for k,v in modules.items()if k in slots}
            if role in ('bus','truck'):
                entrances={k for k,v in modules.items()if 'entrance'in v['name']or 'exit'in v['name']}
                if not entrances<=set(kept):raise ValueError('Station entrances must be retained')
                if not any('platform'in v['name']for v in kept.values()):raise ValueError('At least one station platform is required')
            if role=='warehouse'and not kept:raise ValueError('Warehouse needs at least one storage module')
            changes.append({'role':role,'before':len(modules),'after':len(kept),
                            'removedModuleTypes':sorted({v['name']for v in modules.values()}-{v['name']for v in kept.values()})})
            f['params']['modules']=kept
            # Source expansion slots may have depended on removed modules.
            f['availableExpansionSlots']=[]
    nodes={}
    for r in out['roads']:
        for i in (0,1):
            n=r['node'+str(i)];p=r['position'+str(i)]
            if n in nodes and nodes[n]!=p:raise ValueError('Conflicting node geometry')
            nodes[n]=copy.deepcopy(p)
    ordered=sorted(nodes,key=lambda n:nodes[n]['x'])
    pairs={frozenset((r['node0'],r['node1']))for r in out['roads']}
    if len(pairs)!=len(out['roads'])or pairs!={frozenset(p)for p in zip(ordered,ordered[1:])}:raise ValueError('Only one monotone frontage chain is supported')
    ports={}
    for role in ('bus','truck'):
        p=out.get('rolePortNodes',{}).get(role,[])
        if len(p)!=1 or p[0]not in nodes:raise ValueError('Exactly one observed port per station required')
        ports[role]=p[0]
    left,right=nodes[ports['bus']]['x'],nodes[ports['truck']]['x']
    if right<=left:raise ValueError('Unsupported station order')
    # Carry both ends with their adjacent station and interpolate intermediate
    # nodes. This avoids short doglegs when stations move along the frontage.
    for n,p in nodes.items():
        t=max(0,min(1,(p['x']-left)/(right-left)))
        for k in ('x','y'):p[k]+=(1-t)*shifts['bus'][k]+t*shifts['truck'][k]
    nodes[ordered[0]]['x']-=number(config.get('frontExtension',0))
    nodes[ordered[-1]]['x']+=number(config.get('outerExtension',0))
    directions={};lengths={}
    for a,b in zip(ordered,ordered[1:]):
        p,q=nodes[a],nodes[b];dx,dy=q['x']-p['x'],q['y']-p['y'];length=math.hypot(dx,dy)
        if dx<2 or length<2:raise ValueError('Configuration reverses or collapses the frontage')
        directions[a,b]=(dx/length,dy/length);lengths[a,b]=length
    tangents={}
    for i,n in enumerate(ordered):
        ds=[]
        if i:ds.append(directions[ordered[i-1],n])
        if i+1<len(ordered):ds.append(directions[n,ordered[i+1]])
        x,y=sum(d[0]for d in ds),sum(d[1]for d in ds);length=math.hypot(x,y)
        tangents[n]=(x/length,y/length)
    for r in out['roads']:
        a,b=r['node0'],r['node1'];p,q=nodes[a],nodes[b];length=math.hypot(q['x']-p['x'],q['y']-p['y']);sign=1 if q['x']>p['x']else -1
        r['position0']=copy.deepcopy(p);r['position1']=copy.deepcopy(q)
        for i,n in enumerate((a,b)):
            tx,ty=tangents[n];r['tangent'+str(i)]={'x':sign*tx*length,'y':sign*ty*length,'z':q['z']-p['z']}
    out['name']=config.get('name','可配置航空集合')
    out['configuration']={'input':copy.deepcopy(config),'moduleChanges':changes,'units':'metres in airport-local XY',
                          'sourceTemplateDigest':hashlib.sha256(json.dumps(template,sort_keys=True).encode()).hexdigest()}
    out['sourceEvidence']['note']='Provenance only: original entities do not have the configured layout/modules'
    out['sourceCoverage']={};out['sourceRoadConnected']={}
    out.update(nativeJointPreviewPassed=False,constructionAuthorized=False,requiresNativePortRefresh=True)
    out['requirements']+=['Recompute native entrance geometry after module changes',
                          'Recheck footprint, upgrade clearance, terrain, stock types and pedestrian/vehicle paths']
    compile_spec(out) # Confirm compatibility with the joint preview compiler.
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--template',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.template.resolve().is_relative_to(a.output.resolve())or a.config.resolve().is_relative_to(a.output.resolve()):raise ValueError('Output must be separate from inputs')
    t=configure(json.loads(a.template.read_text('utf8')),json.loads(a.config.read_text('utf8')))
    write_json(a.output/'hub_template.json',t);write_json(a.output/'joint_spec.json',compile_spec(t));atomic_write(a.output/'layout.svg',diagram(t))
    print(json.dumps({'roles':list(f['role']for f in t['facilities']),'moduleChanges':t['configuration']['moduleChanges'],'nativePreviewPassed':False}))
if __name__=='__main__':main()
