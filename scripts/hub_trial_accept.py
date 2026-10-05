"""Final live stock-sharing audit and native save for the authorized trial."""
import asyncio,json,time
from types import SimpleNamespace
from hub_trial import Trial,OUT
from fullmap_batch import batch_lock,quote,StopBatch
from batch_warehouses import write_json

async def main():
 b=Trial(SimpleNamespace(plan=OUT/'plan.json',output=OUT/'execution',action='verify',ids=None,limit=0))
 with batch_lock(b.b.dir):
  tasks=b.tasks();rows=await b.read_facilities(tasks,'verify',with_session=True);entities={}
  for t,r in zip(tasks,rows):
   if not r['result'].get('audit',{}).get('staticVerified'):raise StopBatch('Facility verification failed')
   entities[t['kind']]=r['result']['audit']['entity'];b.ledger['items'][t['id']]['audit']=r['result']['audit']
  code='''local f=B.json.decode(ENTITIES);local CT=api.type.ComponentType;local stocks={};local capacity=0
api.engine.forEachEntityWithComponent(function(id)local w=api.engine.getComponent(id,CT.WAREHOUSE);if w.construction==f.warehouse then stocks[id]=true;stocks[w.stockList]=true;local l=api.engine.getComponent(w.stockList,CT.STOCK_LIST);for _,s in ipairs(l.stocks)do capacity=capacity+s.capacity end end end,CT.WAREHOUSE)
local out={capacity=capacity,facilities=f,coverage={},moduleCounts={}}
for kind,id in pairs(f)do local c=api.engine.getComponent(id,CT.CONSTRUCTION);local n=0;for _ in pairs(c.params.modules)do n=n+1 end;out.moduleCounts[kind]=n
if kind~='warehouse'then local covered=false;for _,st in ipairs(c.stations)do for _,v in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(st,true))do if stocks[v]then covered=true end end end;out.coverage[kind]=covered end end
return B.json.encode(out)'''.replace('ENTITIES',quote(entities))
  result=await b.eval(code)
  if not all(result['coverage'].values()):write_json(OUT/'acceptance_failed.json',result);raise StopBatch('Shared warehouse coverage failed')
  result.update(operationalAccepted=False,linesCreated=0,vehiclesPurchased=0,airportRoadLinkVerified=b.ledger['items']['TRIAL_airport_frontage']['audit']['airportRoadLinkVerified'],publicRoadVerified=b.ledger['items']['TRIAL_public_access']['audit']['verified'],position=b.p['candidate']['origin'])
  if not result['airportRoadLinkVerified']or not result['publicRoadVerified']:raise StopBatch('Road audit incomplete')
  b.ledger['trialAcceptance']=result;b.flush();await b.save('trial_complete');result['save']=b.ledger['events'][-1];write_json(OUT/'result.json',result)
  before=next(e for e in b.ledger['events']if e.get('phase')=='before');result['beforeSave']=before['nativeSaveRequested'];write_json(OUT/'result.json',result)
  report=f'''# 重庆航空货运集合试建

已在重庆北侧完成一组三设施试建，机场原点约 (-2650, 2050)。使用已有的逐项预览/单次提交接口，非多建筑与道路的单个原生原子提交。

- 直升机场：{entities['heliport']}，保留 1 个扩展降落平台模块；机场含购机与维护功能。
- 货运站：{entities['truck']}，保留 12 个货运平台模块和 1 个出入口模块。
- 仓库：{entities['warehouse']}，本次捕获的最新模板有 {result['moduleCounts']['warehouse']} 个模块，读回总容量 {result['capacity']}。
- 机场、货站共同覆盖新仓库库存：通过。
- 通往既有公路的平滑接路、机场前沿道路：均建成，CAR/TRUCK 双向路口检查及机场自动连接通过。

## 与源模板的差异

道路没有复用原址共用接点。原生克隆货站的外接道路长度与已手动编辑的源站不同，源道路预览不能代表克隆后的接入。首次实际接路预览被拒绝且未提交；改用平滑曲线和 `country/country_new_small` 后通过。新道路不是源模板的中型公路原样复制。

本次只复制现有扩展，不额外增加新的扩展模块。预留空地是估算，进一步升级须按实际模块重做碰撞和接路检查。

## 保存与验收范围

- 施工前备份：`{before['nativeSaveRequested']}.sav`
- 最终存档：`{result['save']['nativeSaveRequested']}.sav`，已确认更新并写入稳定。
- 未创建线路、未购车、未运行模拟；静态和连接验收不代表已经开始配送，也不证明长期模拟安全。

证据：`execution/ledger.json`、`result.json`、`plan.json`。源集合保持独立，未改造源设施。
'''
  (OUT/'RESULT.md').write_text(report,encoding='utf8');print(json.dumps(result,ensure_ascii=True))
asyncio.run(main())
