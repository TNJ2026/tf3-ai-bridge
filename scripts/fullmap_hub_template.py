"""Export an existing expanded hub as relative geometry; no game access or commits."""
import argparse,copy,json,math
from pathlib import Path
from fullmap_workflow import write_json,atomic_write


def compile_template(capture):
    if capture.get('captureRequiresRoadSelection') and not capture.get('internalRoadEdgeIds'):
        raise ValueError('Explicit internal road selection required before compiling capture')
    fs=capture['facilities'];roles={f['role']:f for f in fs}
    anchor='helipad'if 'helipad'in roles else'heliport'
    allowed={anchor,'truck','warehouse'}|({'bus','road_depot','road_maintenance'}if anchor=='heliport'else {'helipad2'})
    if not {anchor,'truck','warehouse'}<=set(roles) or set(roles)-allowed or len(fs)!=len(roles):raise ValueError('Expected one facility per role')
    airport=roles[anchor];origin=airport['position'];angle=math.atan2(airport['transform'][0]['y'],airport['transform'][0]['x']);cs,sn=math.cos(angle),math.sin(angle)
    def local(p,vector=False):
        x=p['x']-(0 if vector else origin['x']);y=p['y']-(0 if vector else origin['y']);z=p['z']-(0 if vector else origin['z'])
        return {'x':cs*x+sn*y,'y':-sn*x+cs*y,'z':z}
    own={f['entity']for f in fs};truck=roles['truck'];edges=capture['edges'];frozen=set(truck['frozen_edges']);internal=set(truck['frozen_nodes'])
    ports={e[k]for e in edges if e['id']in frozen for k in ('node0','node1')}-internal
    role_ports={'truck':ports.copy()}
    if 'bus'in roles:
        bus=roles['bus'];bp={e[k]for e in edges if e['id']in set(bus['frozen_edges'])for k in ('node0','node1')}-set(bus['frozen_nodes'])
        role_ports['bus']=bp;ports |= bp
    if 'road_depot'in roles:
        depot=roles['road_depot'];dp={e[k]for e in edges if e['id']in set(depot['frozen_edges'])for k in ('node0','node1')}-set(depot['frozen_nodes'])
        role_ports['road_depot']=dp;ports |= dp
    # Capture the observed local component, but never copy construction-owned roads.
    nodes=set(ports);selected=[]
    while True:
        allowed_edges=capture.get('internalRoadEdgeIds')
        new=[e for e in edges if e['construction']<0 and (allowed_edges is None or e['id']in allowed_edges) and e not in selected and(e['node0']in nodes or e['node1']in nodes)]
        if not new:break
        selected+=new
        nodes.update(e[k]for e in new for k in ('node0','node1'))
    if not selected:raise ValueError('No connected external road component captured')
    names={n:'N'+str(i)for i,n in enumerate(sorted(nodes))};out=[]
    for f in sorted(fs,key=lambda x:x['role']):
        out.append({'role':f['role'],'resource':f['resource'],'localPosition':local(f['position']),
                    'relativeRotation':math.degrees(math.atan2(f['transform'][0]['y'],f['transform'][0]['x'])-angle),
                    'params':copy.deepcopy(f['params']),'availableExpansionSlots':copy.deepcopy(f['slots']),
                    'compatibleModules':copy.deepcopy(f['compatible_modules'])})
    roads=[{'id':'ROAD'+str(i),'node0':names[e['node0']],'node1':names[e['node1']],
            'position0':local(e['position0']),'position1':local(e['position1']),
            'tangent0':local(e['tangent0'],True),'tangent1':local(e['tangent1'],True),
            'roadTemplate':e['roadTemplate'],'roadStyle':e['roadStyle']}for i,e in enumerate(selected)]
    boundaries=[]
    for n in sorted(nodes):
        incident=[e for e in edges if n in(e['node0'],e['node1'])];localdegree=len(incident)
        degree=max((e['node0Degree']if e['node0']==n else e['node1Degree']for e in incident),default=0)
        foreign=sorted({e['construction']for e in incident if e['construction']>=0 and e['construction']not in own})
        excluded=[e['id']for e in incident if e['construction']<0 and e not in selected]
        if foreign or degree>localdegree or excluded:
            boundaries.append({'node':names[n],'externalConstructionEvidence':foreign,'outsideSurvey':degree>localdegree,'policy':'reconnect_at_destination; do_not_copy_external_facility'})
    stock={v['stockList']for v in capture['stockLists']if v['construction']==roles['warehouse']['entity']}
    coverage={role:any(stock.intersection(row['catchables'])for row in capture['catchment']if row['construction']==roles[role]['entity'])for role in (anchor,'truck','helipad2')if role in roles}
    return {'schema':1,'name':'生产设施直升机坪集合'if anchor=='helipad'else'当前扩展型航空货运集合','anchorRole':anchor,'coordinateFrame':'local XY rotated with aviation facility; relative Z must be revalidated against destination terrain',
            'sourceEvidence':{'state':capture['state'],'origin':origin,'rotation':math.degrees(angle),'facilities':{k:v['entity']for k,v in roles.items()}},
            'facilities':out,'roads':roads,'stationPortNodes':[names[n]for n in sorted(ports)],'externalBoundaries':boundaries,
            'rolePortNodes':{role:[names[n]for n in sorted(ps)]for role,ps in role_ports.items()},
            'sourceRoadConnected':{role:any(e['node0']in ps or e['node1']in ps for e in selected)for role,ps in role_ports.items()},
            'sourceCoverage':coverage,'nativeJointPreviewPassed':False,'constructionAuthorized':False,
            'requirements':['Fresh destination terrain and obstacles','Joint native proposal at destination before construction',
                            'Resolve new truck external port; never reuse source IDs','Verify all shared stock types and capacities',
                            'Verify road turns, airport auto links and external road reachability'],
            'limits':['Existing expansion modules preserved; no extra upgrade modules invented',
                      'Expansion slots are structural possibilities, not reserved collision-free land',
                      'Road styles and tangents preserved; construction-owned entrance generated by native facility',
                      'Source external junctions must be redesigned for each destination']}


def diagram(t):
    pts=[f['localPosition']for f in t['facilities']]+[r[k]for r in t['roads']for k in ('position0','position1')]
    loX=min(p['x']for p in pts)-50;hiY=max(p['y']for p in pts)+50
    width=max(p['x']for p in pts)-loX+60;height=hiY-min(p['y']for p in pts)+60
    def point(p):return (p['x']-loX,hiY-p['y'])
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height+60}" width="1000" role="img">',
         '<style>text{font:10px sans-serif;fill:#202020}.title{font-size:14px}</style>',
         '<text x="12" y="18" class="title">当前集合 · 相对位置与道路示意</text>',
         '<text x="12" y="34">保留现有扩展；圆点仅标位置，不代表建筑占地或原生碰撞预览</text>','<g transform="translate(0 50)">']
    for r in t['roads']:
        a,b=point(r['position0']),point(r['position1']);ta,tb=r['tangent0'],r['tangent1']
        svg.append(f'<path d="M {a[0]} {a[1]} C {a[0]+ta["x"]/3} {a[1]-ta["y"]/3} {b[0]-tb["x"]/3} {b[1]+tb["y"]/3} {b[0]} {b[1]}" stroke="#63758a" stroke-width="3" fill="none"/>')
    names={'heliport':'直升机场','helipad':'直升机坪 1','helipad2':'直升机坪 2','truck':'货运站','warehouse':'仓库','bus':'客车站','road_depot':'公路车库','road_maintenance':'道路维护设施'}
    colors={'heliport':'#3283bd','helipad':'#3283bd','helipad2':'#3283bd','truck':'#d99129','warehouse':'#31835e','bus':'#9b59b6','road_depot':'#946b46','road_maintenance':'#c55353'}
    for f in t['facilities']:
        x,y=point(f['localPosition']);count=len(f['params'].get('modules',{}));role=f['role']
        svg.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{colors[role]}"/><text x="{x+10}" y="{y}">{names[role]} · {count} 模块</text>')
    return '\n'.join(svg+['</g></svg>'])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--capture',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.capture.resolve().is_relative_to(a.output.resolve()):raise ValueError('Keep output separate from capture')
    t=compile_template(json.loads(a.capture.read_text('utf8')));write_json(a.output/'hub_template.json',t);atomic_write(a.output/'layout.svg',diagram(t))
    rows=['# '+t['name'],'','依据一次引擎读取生成。已保存现有扩展、相对位置、道路类型及曲线；未修改游戏。','',
          '| 设施 | 当前模块数 | 说明 |','|---|---:|---|']
    for f in t['facilities']:rows.append(f"| {f['role']} | {len(f['params'].get('modules',{}))} | 完整原生 params 和可用扩展槽位已保存 |")
    rows+=['',f"组内观察到的外部道路 {len(t['roads'])} 段；需在目标位置重新处理的外部边界 {len(t['externalBoundaries'])} 处。货站自带道路由原生建筑生成，未重复复制。",'',
           f"当前机场、货站共用仓库覆盖：{t['sourceCoverage']}。这不等于目标位置可建或已验证所有货品吞吐。",'',
           '现有扩展作为默认模板，不额外添加模块。可用槽位只是结构可能性，不代表已经预留无碰撞扩展区。', '',
           '**本次模板导出只读，未执行施工或目标位置预览。** 不能把源道路实体编号直接用于新位置；外部接路须按新位置设计。', '',
           f"源设施道路几何连接：{t['sourceRoadConnected']}。未连接部分按现状记录，不自动补建；该字段不是车辆/步行路径验收。", '',
           '后续使用：目标位置重新预览；设施放置后重新解析出入口，再逐项接路和验收。此模板不授权建造。', '',
           '[相对布局示意](layout.svg) · [机器可读模板](hub_template.json)','']
    atomic_write(a.output/'README.md','\n'.join(rows));print(json.dumps({'facilities':len(t['facilities']),'roads':len(t['roads']),'externalBoundaries':len(t['externalBoundaries']),'coverage':t['sourceCoverage']},ensure_ascii=True))
if __name__=='__main__':main()
