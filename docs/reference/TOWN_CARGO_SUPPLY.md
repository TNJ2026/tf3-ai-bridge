# 城市面板供给只读接口

`get_town_cargo_supply(town=14672)` 读取城市面板同源的货品供给和需求，无须遍历建筑。要求已加载接收器 `townCargoSupplyVersion=2`；旧版本在发送前拒绝。Python MCP 服务须重新加载以注册新工具。修改代码不自动重载游戏或恢复监控。

原生来源：`api.engine.system.townBuildingSystem.getCargoSupplyAndLimit(town, landUse)`。游戏 `game_mechanics/towns/town_util.tl` 中 `getCargoSupplyDemandsLandUse` 使用需求向下取整、供给向上取整且不超过需求；城市面板的 `town_react_util.tl` 通过并行包装调用这一逻辑。

- `districts`：residential/commercial/industrial，逐真实 cargo ID 返回原始 rawSupply/rawDemand 和面板 supply/demand。
- `items`：按 cargo ID 去重，累加各用地的面板供给和需求，返回 supplyRate（0～1）；先按用地取整后汇总。
- `rateKnown=false`：需求为零，不返回比例，不冒称达到50%。无效或缺失原生数值明确报错，不置零。
- `gameTime`：采样游戏时间；`periodKnown=false`：该 API 未说明统计窗口，不称为年度或半年交付量，也不混除其他窗口数据。
- 仅货品，不包含住宅面板根据 lineUsage 派生的旅客指标；公交仍单独读取。

监控判断应使用本接口面板比例；不再用逐栋年度消费代理比率替代城市面板。接口未加载时报告实际能力缺口，不重发、不恢复监控。

验证：Lua 原生调用模拟、取整与跨用地重复货品、零需求、无效值、参数、旧接收器门槛、MCP路由与引擎事件通道测试通过。尚未在当前游戏加载新版并实测数值，不能称为已实机验收。


首次实机 v1 请求 c8e33a36f07b4e4c8305ecd3fbc83b56 在函数类型保护处报错，未执行供给调用。v2 移除仅接受 Lua function 的错误限制，允许原生可调用 table（含隐藏元表），实际调用失败仍由请求保护捕获，不回退伪造数据。新增可调用 table 回归测试，34项相关测试通过。仓库与实际加载目录均已同步并编译通过，待重载实测；此前不能将该错误解释为执行环境确实缺少原生API。监控保持暂停。


2026-10-13 v2实机验证通过：会话36301.555:table: 0000008105252630，主城临汾14672、玩家14670、世界2。gameTime36992800：鱼45/471、燃料16/451、服装0/235、罐头食品11/235、家具132/225；原生接口成功返回，未逐栋遍历。证据 output/linfen_monitor_20261013/town_supply_v2_live_1791882100.json。已核对源码面板口径，尚待用户肉眼对比；只读查询，保留当前暂停速度及监控暂停状态。
