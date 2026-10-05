"""Offline analysis of a joint native preview. Never invent generated entrance IDs."""
import argparse,json
from pathlib import Path
from fullmap_workflow import write_json,atomic_write

def analyze(spec,result):
    explicit={n['entity']:'road_node' for n in spec['nodes']}
    explicit.update({r['entity']:'road_segment' for r in spec['roads']})
    networks=result.get('networks',[])
    collisions=result.get('collisions')
    complete=isinstance(collisions,list) and isinstance(result.get('errorState'),dict) and 'critical'in result['errorState']
    classified={'existing_world':[],'explicit_roads':[],'generated_or_unmapped':[]}
    if isinstance(collisions,list):
        for entity in sorted(set(collisions)):
            key='existing_world' if entity>=0 else 'explicit_roads' if entity in explicit else 'generated_or_unmapped'
            classified[key].append(entity)
    # Entity incidence is a diagnostic only: directed lane indices and TP links
    # are required for actual vehicle/person path acceptance.
    graph={}
    for row in networks:
        for edge in row['edges']:
            if not set(edge.get('modes',[])).intersection((2,3,4)):continue
            a,b=edge['from']['entity'],edge['to']['entity']
            graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    components=[];unseen=set(graph)
    while unseen:
        stack=[min(unseen)];found=set()
        while stack:
            node=stack.pop()
            if node in found:continue
            found.add(node);stack.extend(graph[node]-found)
        unseen-=found;components.append(sorted(found))
    bindings={}
    for role,binding in spec['portBindings'].items():
        node=binding['roadNode'];component=next((c for c in components if node in c),[])
        bindings[role]={'roadNode':node,'incidenceComponent':component,
                        'sharesEntityIncidenceWithGeneratedNodes':any(n not in explicit for n in component),
                        'nativeEntranceNode':None,'verified':False}
    return {'collisionDiagnosticsComplete':complete,'collisions':classified,
            'vehicleEntityIncidenceComponents':components,'portBindings':bindings,
            'linksInspectable':isinstance(result.get('links'),dict) and '_unavailable'not in result['links'] and
                all(bool(row) for key in ('toAdd','toRemove')for row in result['links'].get(key,[])),
            'nativePreviewClear':complete and not any(result['errorState'].get(k)for k in ('critical','messages','infos','warnings')) and not collisions,
            'connectionsVerified':False,'commitAllowed':False,
            'limitations':['Incidence is undirected and ignores lane indices; not a path test',
                          'Generated entities are not assigned to roles without native ownership evidence',
                          'Uninspected TP links cannot be treated as absent']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--result',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=analyze(json.loads(a.spec.read_text('utf8')),json.loads(a.result.read_text('utf8')))
    write_json(a.output/'diagnosis.json',data)
    rows=['# 联合提案离线诊断','',f"原生预览无错误：{data['nativePreviewClear']}",f"允许提交：{data['commitAllowed']}",'',
          f"既有地图碰撞：{data['collisions']['existing_world']}",f"显式新道路碰撞：{data['collisions']['explicit_roads']}",f"生成或未映射实体碰撞：{data['collisions']['generated_or_unmapped']}",'']
    for role,b in data['portBindings'].items():rows.append(f"- {role}：道路节点 {b['roadNode']}；同一车辆实体关联分量含自动生成节点：{b['sharesEntityIncidenceWithGeneratedNodes']}；入口未绑定，未通过验收。")
    rows+=['','上面是实体关联诊断，不代替有向车道/步行寻路。TP 链接未完整读取时不能认定没有连接。生成实体编号不能写回下次提案。','']
    atomic_write(a.output/'README.md','\n'.join(rows));print(json.dumps(data))
if __name__=='__main__':main()
