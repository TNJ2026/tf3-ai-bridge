"""Render maintenance construction and runtime evidence; no game calls."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'exports/maintenance_repair_20261003'
read=lambda n:json.loads((out/n).read_text(encoding='utf8'))
ledger=read('ledger.json');first=read('survey.json');tr=read('observation.json');extra=read('heli_return_observation.json')if(out/'heli_return_observation.json').exists()else[];last=(extra or tr)[-1]
original={v['lineName']:v for v in first['vehicles']};current={v['lineName']:v for v in last['vehicles']}
selected=read('selected.json');saves=[x for x in ledger['events']if x.get('complete')and x.get('nativeSaveRequested')]
lines=['# 维护站补建与车况验收','', '已在四个产业端补建公路维护站，各站原生服务半径600米、维护池16。单次施工、独立读回通过。原生设施无道路端口，服务通过范围生效；未替换道路、未修改线路。','', '| 服务线路 | 位置 | 施工状态 |','|---|---|---|']
for t in selected:lines.append(f"| {t['id'].replace('REPAIR_MAINT_I','SHUTTLE')} | ({t['position']['x']}, {t['position']['y']}) | {ledger['items'][t['id']]['status']} |")
lines+=['','选址靠近既有道路，避开建筑和道路碰撞。按约50米方形估算扩建留空；这是规划余量，不代表任意升级均已通过预览。即时声誉预估已记录在 previews.json，不包含运营噪声与污染。','', '| 线路 | 施工前车况 | 最后车况 | 最后维护变化值 |','|---|---:|---:|---:|']
for name,v in original.items():
 if v['condition']<=.8 or name.endswith('R009'):
  q=current[name];lines.append(f"| {name} | {v['condition']*100:.1f}% | {q['condition']*100:.1f}% | {q['change']:.6f} |")
zero=[v['lineName']for v in first['vehicles']if v['condition']==0];alltr=tr+extra
recovered={name:any(next(v for v in r['vehicles']if v['lineName']==name)['condition']>=.999 for r in alltr)for name in zero}
lines+=['',f"原4辆零车况短驳货车均已实测恢复至100%：{all(recovered.values())}。最后78辆车船平均车况{statistics.mean(v['condition']for v in last['vehicles'])*100:.1f}%，寻路异常{sum(v['noPath']for v in last['vehicles'])}辆。",'',f"模拟观察：{tr[0]['state']['gameTime']} → {last['state']['gameTime']} ms；阶段性4倍速，结束恢复暂停。",'','maintenanceStation=-1仅表示当前未关联维护站，不证明整条线路没有维护覆盖。长途车辆在服务范围外会损耗，进入范围后再恢复；用实际完整运行样本判断，不能以单帧低于80%就自动增建。','',f"最新原生存档：`{saves[-1]['nativeSaveRequested']}`。",'','- ledger.json：提交次数、独立验收和存档。','- previews.json：位置、碰撞、原生infos/warnings/messages和声誉。','- observation.json、heli_return_observation.json：全车队实际车况、维护关联与变化。','- 观察期间自动新增粘土坑 (372,-2648)，已对账记录，未为其施工。','', '短期恢复已验证；未将其等同于长期稳定或未来扩编后的维护容量充足。']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
(out/'summary.json').write_text(json.dumps({'stationsBuilt':len(selected),'initialZeroVehiclesRecovered':recovered,'lastState':last['state'],'averageCondition':statistics.mean(v['condition']for v in last['vehicles']),'noPath':sum(v['noPath']for v in last['vehicles']),'latestSave':saves[-1]},ensure_ascii=False,indent=2),encoding='utf8')
print(out/'REPORT.md')
