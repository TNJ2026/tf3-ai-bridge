# 道路电车／公交车道升级实测（2026-10-15）

用户在得知现有升级入口仅有结构预览、无完整报价与碰撞预览后要求“在道路上验证下”。本轮在当前地图新建两条独立测试道路，不修改运营道路。

## 现场与结果

- 测试区 x=-2300～-2000；电车道路 y=-2800，公交道路 y=-2700。每组300米、三段各100米，初始均为 `town/town_new_medium`。
- 基础道路原生预览通过，无碰撞或警告，报价239472元；先保存 `wareham_before_lane_upgrade_20261015`，再刷新预览、单次建造并读回。见 [基础施工](construction.json)。
- 六段分别经过 `preview_road_upgrade` → `commit_edge_edit`，均 `applied=true / verified=true`。独立读取 BASE_EDGE，逐项比较两端节点、位置与切线，保持不变。见 [升级日志](upgrades.json)。
- 电车组目标 `town/town_new_medium_tram_electrified`，最终边7999、28514、28520；原生外侧车道支持 TRAM/ELECTRIC_TRAM，并保留普通机动车通行。
- 公交组目标 `town/town_new_medium_bus`，最终边28509、28510、28515；外侧车道允许 BUS/TRUCK，不允许 CAR，内侧仍允许普通汽车。它不是仅公交车辆可用的专用道。见 [实际车道读回](lane_summary.json)。
- 电车组两路口分别检查 TRAM/ELECTRIC_TRAM/CAR 两向，公交组两路口分别检查 BUS/TRUCK/CAR 两向，共24项原生查询全部 `pathFound=true / directPathVerified=true`。原始证据为本目录 `path_*.json`。

## 边界与收尾

升级预览仍是 `validation=structural_only`、`costAvailable=false`、碰撞留给原生提交拒绝处理。此次原生接受并读回成功，不表示接口已新增完整报价或碰撞预览。未知费用保持未知，未由余额不变推断免费；普通预算项目仍须遵守报价要求，本测试记录不授权其他项目跳过保护。

本轮仅验证普通无附属对象地面道路整段模板替换，不包括带站牌路段、建筑内部道路、桥隧、逐车道自由编辑或电车与公交组合模板。没有车辆实跑、模拟推进或重载验收。

最终暂停、无pending，游戏时间6130400；即时现金34303124元、贷款15516659元，未新增贷款。完工槽 `wareham_lane_upgrade_verified_20261015` 已确认新文件非空稳定，见 [保存记录](final_save.json)。测试道路保留，未恢复监控。
