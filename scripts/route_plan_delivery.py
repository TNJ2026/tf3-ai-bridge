"""Compile read-only route evidence, explicit assumptions and an execution manifest."""
import argparse
import collections
import datetime
import json
import math
from pathlib import Path
from types import SimpleNamespace
from fullmap_lines import Lines
from fullmap_batch import write_json

def distance(a,b):return math.hypot(a['x']-b['x'],a['y']-b['y'])

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--native',type=Path,required=True)
    ap.add_argument('--base-report',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();root=a.output
    p=json.loads(a.plan.read_text(encoding='utf8'))
    b=Lines(SimpleNamespace(plan=a.plan,output=a.native,action='preview',line_ids=None,ids=None))
    specs={v['id']:v for v in b.specs()}
    support=json.loads((a.native/'support.json').read_text(encoding='utf8'))
    services={v['id']:v for v in support['lines']}
    models={m['model']:m for m in json.loads((root/'models.json').read_text(encoding='utf8'))['models']}
    details=json.loads((root/'inputs/details.json').read_text(encoding='utf8'))
    cargos={c['id']:c for c in details['cargos']};demands=collections.Counter()
    for building in details['buildings']:
        for key,value in (building.get('demands') or {}).items():demands[int(key)]+=value
    demand_changed=any(abs(demands[s['cargo']]-s['demand'])>=.001 for s in p['supply'])
    names={f"T{v['id']}":v['name'] for v in p['cities']}
    industry_names={'farm':'农场','livestock_farm':'畜牧场','forest':'林场','saw_mill':'锯木厂',
        'oil_platform':'海上油井','oil_refinery':'炼油厂','clay_pit':'黏土矿','bricks_works':'砖厂','fishing_grounds':'渔场'}
    for i in p['industries']:names[f"I{i['id']}"]=industry_names.get(i['resource'].split('/')[-2],str(i['id']))
    def label(key):
        if isinstance(key,dict):return names['I'+str(key['existing_industry'])] if 'existing_industry' in key else names['T'+str(key['town'])]+'市内配送'
        owner=key.split('_')[0]
        return (names.get(owner,'捕鱼港')+'集合/'+key[len(owner)+1:])
    rows=[];totals=collections.Counter();report=json.loads(a.base_report.read_text(encoding='utf8'));report['routes']=[]
    for l in p['line_specs']:
        spec=specs[l['id']];native=b.ledger['items'][l['id']]['preview'];svc=services[l['id']]
        assert native['stops'] and b.ledger['items'][l['id']]['attempts']==0
        points=[e.get('position') or e['stop']['position'] for e in spec['endpoints']]
        geometric=sum(distance(point,points[(i+1)%len(points)]) for i,point in enumerate(points))
        length=geometric
        speed={'TRUCK':9,'HELICOPTER':45,'SMALL_SHIP':7}[l['mode']]
        dwell={'TRUCK':45,'HELICOPTER':120,'SMALL_SHIP':90}[l['mode']]
        cycle=length/speed+len(points)*dwell;model=models[l['vehicle_model']]
        quantity=sum(l['cargos'].values());fleet=max(1,math.ceil(quantity*1.25*cycle/(1460*model['capacity'])))
        purchase=min(svc['purchaseCandidates'],key=lambda d:distance(d,points[0]))
        fallback=None
        if not svc['maintenanceCandidates']:
            candidates=[d for d in svc['purchaseCandidates'] if d.get('pool',0)>0]
            if candidates:
                base=min(candidates,key=lambda d:distance(d,points[0]));fallback=dict(base=base,
                    policy='维护基地候选；维护方式未配置，不额外验证返库',
                    lowerBoundReturnDistance=2*distance(base,points[0]))
        stops=[]
        for s in native['stops']:
            allowed=set(s['loads'])
            stops.append(dict(s,cargoLoadByLuaIndex={str(c+1):c in allowed for c in cargos},maxLoad=1,forceUnload=False))
        row=dict(l,name=label(l['source'])+' → '+label(l['destination']),resolvedStops=stops,
            path=points,closedPathVerified=False,nativeNetworkLength=None,distanceForecast=length,
            distanceBasis='coordinate estimate; not actual network distance',forecastIsAcceptanceGate=False,
            vehicle=model,fleet_forecast=fleet,cycle_seconds_forecast=cycle,purchaseBase=purchase,
            maintenanceEvidence=svc['maintenanceCandidates'],maintenanceFallback=fallback,
            operationalAccepted=False,constructionAuthorized=False,
            fleetAssumptions=dict(demandPeriodSeconds=1460,periodVerified=False,speedMps=speed,dwellPerStopSeconds=dwell,reserveFactor=1.25,
                notes='初始估算：年度需求按既有规划的1460秒周期假设；未含实际排队、维护停运和水路绕行，开通后按实测速率调整'))
        row['purchase_base']=purchase['depot'];row['maintenance_base']=None
        rows.append(row);totals[l['mode']]+=fleet
        report['routes'].append(dict(name=l['id']+' '+row['name'],mode=l['mode'],status='兼容终端已选；未开通',length=round(length),path=points,
            warning='直线示意里程；'+('维护接驳候选' if fallback else '端点维护覆盖已查询，沿途未查')))
    splits=collections.defaultdict(list)
    for row in rows:
        if row.get('parallel_split',1)>1:splits[tuple(row['flows'])].append(row)
    for group in splits.values():
        for side in (0,-1):
            assert len({(r['resolvedStops'][side]['group'],r['resolvedStops'][side]['station'],r['resolvedStops'][side]['terminal']) for r in group})==len(group)
    flow_checks=[]
    for flow in p['routes']:
        # Every transfer stage carries the same allocated goods; sum only parallel lines within a stage.
        matched=[r for r in rows if flow['id'] in r['flows']]
        flow_checks.append(dict(flow=flow['id'],annual=flow['annual'],lines=[r['id'] for r in matched],
            note='联运各段重复承载同一批货，不能跨段累加为新增供给；线路聚合货量包含其他同货品流'))
    manifest=dict(schema=1,plan=str(a.plan.resolve()),session=support['session'],authorization='仅规划，不创建线路或购买车辆',
        lines=rows,flowAccounting=flow_checks,vehicleTotalsForecast=dict(totals),supply=p['supply'],
        demandForecastChanged=demand_changed,
        unresolved=['维护覆盖不等于维护吞吐或长期模拟安全', '车型载量与可用年份已读取；购车前逐货品核对装载配置',
            '1460秒需求周期未验证；直线里程及运力数量仅为估算', '时效与吞吐估算不作为投运门槛'],
        executionOrder=['取得线路和购车授权后保存施工前备份','重新解析当前会话、实体及终端并重做原生预览',
            '逐条单次创建线路，初始化全部货品装卸数组，读回核对','车型货品兼容及维护接驳确认后，从指定基地分批购车',
            '确认实际出库、正常执行所配线路且无原生故障即完成投运验收','验收并写入同一地图的固定自动存档槽'])
    write_json(root/'execution_manifest.json',manifest)
    report.update(sites=[],phases=[dict(name='线路开通',actions='重新预览后逐条创建并核对装卸',gate='用户授权创建线路'),
        dict(name='购车及运营验收',actions='货品兼容、维护接驳、分批投放及运行标定',gate='用户授权购车且运行前检查通过')],
        title=f'全图货运线路规划 · {len(rows)}条兼容终端已选（未开通）',createdAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        warnings=manifest['unresolved']+['地图设施背景取自本轮建造前快照；路线端点已绑定当前已建设施。图上连线为走廊示意，不是实际道路轨迹。'],supply=p['supply'])
    write_json(root/'report_plan.json',report)
    text=['# 当前地图货运线路规划','', f'仅规划：未创建线路、未购买车辆。{len(rows)}条线路已选择兼容终端；尚未投运验收。',
        '', '车型：GMC 660 DFM 通用卡车（22）、H-21 直升机（12）、Votrans 拖船式货轮（30）；括号为当前模型载量。',
        '', f'首轮运力估算：货车 {totals["TRUCK"]}、直升机 {totals["HELICOPTER"]}、货船 {totals["SMALL_SHIP"]}。这不是自动购车数量：需求周期暂沿用1460秒假设，未计实际维护停运、拥堵和水路绕行。',
        '', '|编号|线路|货品及规划量|初估车辆|维护安排|','|---|---|---|---:|---|']
    for r in rows:
        cargo='、'.join(f'{cargos[int(k)]["name"]} {v:.1f}' for k,v in r['cargos'].items())
        text.append(f'|{r["id"]}|{r["name"]}|{cargo}|{r["fleet_forecast"]}|'+('维护基地候选' if r['maintenanceFallback'] else '端点维护查询见清单')+'|')
    text+=['','所有线路仅在来源装载列出的货品，目的地允许正常卸货且禁止装货；不强制卸货。城市配送逐站卸货后返回。',
        '', '谷物双航线各49，共98；渔港两条供鱼航线使用两个独立停机坪；厦门、石家庄各自两路航空收货使用不同终端。未新增货量，不建立同集合航空自环。',
        '', '供给缺口：鱼29、燃料26.932、砖石40；蔬菜、肉类、厚木板按当前需求可配足。资源类型齐全，暂无缺类型勘探任务。',
        '', '客运不在本次货运清单中；现有客运设施需另做出行需求与公交接驳规划。',
        '', '## 执行与验收','', '路线与站点明细、终端编号、装载数组、采购基地、维护接驳和假设均见 `execution_manifest.json`。',
        '', '只读复核入口：`fullmap_lines.py preview --plan <route_plan_v2.json> --output <native_v2>`，随后 `route_support_preview.py --plan <同一文件> --output <同一目录>`。',
        '', '授权开通后，`fullmap_lines.py build` 可逐条预览、单次提交并读回装卸配置；不得直接重放导出的历史实体。购车单独执行，旧 `fullmap_vehicles.py` 仅按每线一辆，不可用于此清单的批量运力部署。',
        '', '本轮仅查询端点维护覆盖；未覆盖不代表全线无维护。不做额外返库、完整往返或交付数量验收；预测不等于长期运行安全。']
    (root/'ROUTES.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    print(json.dumps({'lines':len(rows),'vehiclesForecast':dict(totals),'maintenanceFallback':[r['id'] for r in rows if r['maintenanceFallback']]}))

if __name__=='__main__':main()
