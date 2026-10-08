"""Render execution summary from recorded results; does not connect to the game."""
import json,collections
from pathlib import Path
from fullmap_batch import ROOT,write_json
out=ROOT/'exports/fullmap_plan_20261003/execution';ledger=json.loads((out/'ledger.json').read_text(encoding='utf8'));plan=json.loads((out.parent/'network_plan.json').read_text(encoding='utf8'));names={c['id']:c['name']for c in plan['cities']};items=ledger['items'];ops=json.loads((out/'current_operations.json').read_text(encoding='utf8'))if(out/'current_operations.json').exists()else{}
fac=collections.Counter(v['kind']for v in items.values()if v.get('status')=='static_verified'and v['kind']not in ['line','vehicle','street_stop']);modes=collections.Counter(v.get('audit',{}).get('mode')for v in items.values()if v['kind']=='vehicle'and v.get('status')=='static_verified')
saves=[e for e in ledger['events']if e.get('complete')and e.get('nativeSaveRequested')];towns=[dict(r,name=names.get(r['town'],str(r['town'])))for r in ops.get('townSupply',[])];supplied=[r for r in towns if r['supply']>0];unsupplied=[r['name']for r in towns if r['supply']==0]
status={'complete':False,'operationalAccepted':False,'facilities':dict(fac),'facilityTotal':sum(fac.values()),'roadConnections':sum(v['kind']=='connection'and v.get('status')=='connection_verified'for v in items.values()),'newStopPairs':sum(v['kind']=='street_stop'and v.get('status')=='static_verified'and not v.get('alias')for v in items.values()),'reusedStopPairs':sum(v['kind']=='street_stop'and bool(v.get('alias'))for v in items.values()),'lines':sum(v['kind']=='line'and v.get('status')=='static_verified'for v in items.values()),'vehicles':dict(modes),'vehicleTotal':sum(modes.values()),'townSupply':towns,'townsWithSupply':len(supplied),'townsWithoutObservedSupply':unsupplied,'noPath':ops.get('noPath'),'lastState':ledger.get('lastState'),'latestNativeSave':saves[-1]if saves else None,'remaining':['Full-cycle capacity, freshness and maintenance acceptance; first fleet is one vehicle per active line','Automatically spawned industries outside original 18-industry construction manifest'] }
write_json(out/'status.json',status)
coverage=json.loads((out/'city_coverage.json').read_text(encoding='utf8'));covered=sum(r['coveredStocks']for r in coverage);stocks=sum(r['stocks']for r in coverage)
text=f"""# 全图执行状态

原规划基础设施和首批车队已补齐；当前仍为**运行验收未完成**，不是全图所有需求满足。游戏已在运行观察后暂停，原生存档见下文。

## 已建设与静态验收

- {sum(fac.values())}处设施：总部1、公路车库6、货运汽车站30、仓库30、直升机坪27、直升机购置/维护基地8、道路维护站20、码头3、船坞{fac.get('water_depot',0)}。
- {status['roadConnections']}条实际接路，通过CAR/TRUCK双向原生路径验收；总部与维护站等21项没有原生公路端口，不虚构连接道路。
- {status['newStopPairs']}组双向卸货点；另1个同路段计划点复用已建站点，覆盖其全部目标建筑。
- {status['lines']}条货运线路，原生闭合路径和完整装载向量验收通过；原计划全部线路已配首批车辆。
- 首批{status['vehicleTotal']}辆：货车{modes.get('TRUCK',0)}、直升机{modes.get('HELICOPTER',0)}、船舶{modes.get('SMALL_SHIP',0)}。每条投入线路1辆，未直接按预测运力扩购。
- 最近城市覆盖审计：{covered}/{stocks}个有需求库存点在实际卸货站覆盖内。覆盖不是供给满足率，城市增长后需要再审计。
- 27组货站—仓库—直升机坪、3组码头—仓库—货站的实际库存覆盖已经通过。

## 实际运行证据

已按受控时段推进模拟，保存逐次车辆装货、状态、寻路和城市供给。最近读回报告寻路错误的车辆：{len(ops.get('noPath',[]))}个；城市原生供给统计已出现正值的城市共{len(supplied)}座：{ '、'.join(r['name']for r in supplied)or '暂无' }。

城市供给采用原生`townBuildingSystem.getCargoSupplyAndLimit`（城市界面同口径）。早期观察文件中的库存`deliveredPerYear=0`不能推导城市未收货；中间样本没有采城市指标时标记为空，不能当0。详见 `current_operations.json` 和 `observation_*.json`。

两艘新增船舶在本轮观察中各装载30件货物，随后到港载量降至0；逐帧样本见 `ship_completion_acceptance.json`，这尚不等于对应城市已经收货。

## 待运行验收

1. 三座船坞均已建成，三条水运线均已购船。海岸线误判根因是漏读原生 `errorState.infos`；当前批量执行器和共用预览已修正。第二座采用75°朝向的新修订；旧失败操作保留、不重发。
2. 首批车辆能实际装货并为部分城市提供供给，尚未完成所有城市/所有货物、完整循环时效、长期维护与运力扩容验收。原规划产能上限与易腐货物风险仍需单独处理。当前未观察到正供给的城市：{ "、".join(unsupplied) }。
3. 运行中自动新增产业不在原施工清单内；已核对的会话增量记录在 ledger.json 的 sessionAdditions。它们尚未完成配送规划与建设。

## 存档与记录

最新原生存档：`{saves[-1]['nativeSaveRequested']if saves else '无'}`。

路径：`{saves[-1].get('file','')if saves else ''}`。

- `ledger.json`：逐项提交、协调、验收和全部存档记录。
- `facility_amendments.json`、`road_amendments.json`：岸线及接路调整，原方案不覆盖。
- `city_coverage.json`、`hub_coverage.json`：城市末端与仓库中转覆盖。
- [批量脚本说明](../../../scripts/FULLMAP_BATCH.md)：分类执行方式和边界。

短时运行无报错不证明长期模拟安全，未声称历史MakePersonCapacityData断言根因已修复。未重载存档测试。
"""
(out/'STATUS.md').write_text(text,encoding='utf8');print(json.dumps({k:status[k]for k in ['facilityTotal','roadConnections','lines','vehicleTotal','townsWithSupply']},ensure_ascii=False))
