"""Generate map-independent planning deliverables from the current pack; offline only."""
import argparse,csv,io,json
from datetime import datetime, timezone
from pathlib import Path
from fullmap_workflow import write_json,atomic_write
from tf3_mcp.planning_geometry import facility_aabb
def write_report(output):
    p=json.loads((output/'network_plan.json').read_text('utf8'))
    s=json.loads(Path(p['snapshot']).read_text('utf8'))
    facilities=p['facilities']+p.get('ports',[]);towns={t['id']:t['name']for t in p['cities']}
    title=towns[p['focus_town']]+'主城 · 全图货运规划（含已建复用设施）' if any(f.get('reuseOnly') for f in facilities) else towns[p['focus_town']]+'主城 · 全图货运规划（候选）'
    def table(headers,rows):
        return '\n'.join('| '+' | '.join(str(v).replace('|','/')for v in row)+' |'for row in [headers,['---']*len(headers)]+rows)+'\n'
    def csv_file(name,headers,rows):
        stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(headers);writer.writerows(rows);atomic_write(output/name,stream.getvalue())
    csv_file('FACILITIES.csv',['id','kind','x','y','rotation'],[[f['id'],f['kind'],f['position']['x'],f['position']['y'],f['rotation']]for f in facilities])
    csv_file('LINES.csv',['id','mode','source','destination','annual_cargos','source_terminal','destination_terminal','fleet_forecast'],[[l['id'],l['mode'],json.dumps(l['source'],ensure_ascii=False),json.dumps(l['destination'],ensure_ascii=False),json.dumps(l['cargos']),l.get('source_terminal_index'),l.get('destination_terminal_index'),l.get('fleet_forecast')]for l in p['line_specs']])
    supply=[x for x in p['supply']if x['demand']]
    atomic_write(output/'SUPPLY.md','# 当前地图供给\n\n'+table(['货物','需求/年','原料约束后产能/年','分配/年','缺口/年'],[[x['name'],x['demand'],x['available'],x['allocated'],x['gap']]for x in supply])+'\n理论产能及分配不是实际交付。产量不足不等于地图缺少该资源种类；勘探必须依据当前完整资源清单，不能从缺口直接推断。此报告不声明已勘探或已施工。\n')
    atomic_write(output/'CITIES.md','# 当前城市集合\n\n'+table(['城市','集合','锚点XY/m','建成区退距/m'],[[towns[h['entity']],h['owner'],f"{h['position']['x']:.1f}, {h['position']['y']:.1f}",round(h.get('city_boundary_distance_m',0),1)]for h in p['hubs']if h['kind']=='city'])+'\n近/长期增长范围和共享产业映射保存在network_plan.json；增长是估算。500米不是已验证的噪声安全距离，共用集合仍须货车配送和吞吐验收。\n')
    quantity=p.get('collection_quantity_decisions',{})
    atomic_write(output/'CITY_SITING_REVIEW.md','# 城市集合统筹比较\n\n'+table(['集合对','锚点间距/米','状态'],[[','.join(v['owners']),round(v['anchor_distance_m']),v['status']]for v in p.get('city_siting_reviews',[])])+ '\n相邻或服务范围可能重复时，比较共用一套、保留分建、移近服务城市三种方案。真实道路往返、合计吞吐、覆盖、噪声污染、扩建与城市增长均须有依据；不能仅凭建筑预览通过放行。1000 米是复核触发值，不是最小间距。\n')
    atomic_write(output/'COLLECTIONS.md','# 集合数量与服务归属\n\n'+
        table(['陆上候选','数量决策','需复核吞吐'],[[d['owner'],d['decision'],d['requires_capacity_review']]for d in quantity.get('decisions',[])])+'\n'+
        table(['捕鱼港口','服务渔场','合计运量/年','超过规划吞吐预算'],[[v['id'],','.join(map(str,v['service_industries'])),v['annual_forecast'],v['capacity_review'].get('forecast_exceeds_budget',False)]for v in p.get('ports',[])])+'\n'+
        table(['对象类型','对象','运输服务状态'],[[v['kind'],v['entity'],v['status']]for v in quantity.get('service_inventory',[])])+ '\n无分配运量不等于无需服务，须结合供给缺口检查。航路是粗网格初筛；真实往返航路、维护、共同库存、终端及吞吐仍须原生验收。已有集合须显式登记与核验，不自动拆除。\n')
    fm={f['id']:f for f in facilities};sites=[]
    def bounds(members,key):
        boxes=[facility_aabb(fm[f],key) for f in members]
        return {end:{axis:(min if end=='min' else max)(b[end][axis] for b in boxes) for axis in ('x','y')} for end in ('min','max')}
    # One label per collection avoids dozens of overlapping per-facility labels.
    grouped={v for h in p['hubs']for v in h['facilities'].values()}
    for h in p['hubs']:
        members=h['facilities'].values()
        sites.append(dict(name=towns.get(h['entity'],h['owner'])+'集合',current=bounds(members,'footprint'),reserved=bounds(members,'reserved'),status='候选；待当前原生预览',conflicts=[],siteConflicts=[]))
    for port in p.get('ports',[]):
        members={port['id'],port['warehouse'],port['helipad'],port['helipad2'],port['maintenance_base'],port['purchase_base']}
        grouped.update(members)
        sites.append(dict(name=port['id']+' 捕鱼集合（渔场 '+','.join(map(str,port['service_industries']))+'）',current=bounds(members,'footprint'),reserved=bounds(members,'reserved'),status='候选；待航路、吞吐与联合预览',conflicts=[],siteConflicts=[]))
    sites += [dict(name=f['id'],current=facility_aabb(f,'footprint'),reserved=facility_aabb(f,'reserved'),status='已建复用；执行前重新解析验收' if f.get('reuseOnly') else '候选；待当前原生预览',conflicts=[],siteConflicts=[])for f in facilities if f['id']not in grouped]
    write_json(output/'report_plan.json',dict(scope='global',title=title,createdAt=datetime.now(timezone.utc).isoformat(),snapshot=s,sites=sites,
        phases=[dict(name='施工前复核',actions='当前会话重新解析实体并完成联合原生预览',gate='全部依赖与接点明确且获得对应施工授权'),dict(name='分阶段施工及验收',actions='单次提交、读回；依赖建成后绑定真实端口',gate='共享库存覆盖、双向路径与持续模拟验证通过')],
        routes=[dict(name=r['id'],mode=r['mode'],path=r['path'],status='联系示意',warning='道路运输沿道路通行；不是可直接施工的走廊')for r in p['routes']],
        supply=[dict(name=x['name'],effectiveDelivery=x['allocated'],unmetDemand=x['gap'],time_unit='游戏年',evidence='当前输入与估算')for x in supply],
        warnings=['离线候选；当前原生预览及真实端口/库存/双向路径验收仍需完成。','已建复用设施以计划登记为准；资源产能缺口不等于资源种类缺失。']))
    from planning_delivery import write_delivery
    write_delivery(output,p)
    return {'facilities':len(facilities),'lines':len(p['line_specs']),'gameCalls':0}
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();print(json.dumps(write_report(a.output)))
if __name__=='__main__':main()
