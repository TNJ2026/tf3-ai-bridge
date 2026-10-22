# 双侧停靠点（零污染·零噪音）

当前状态（2026-10-22，v0.12.119 / revision95）：已按用户要求撤销全部道路及附加资源属性覆盖，并从源码和 staging 移除全部新增道路、车辆、直升机与设施。本页以下配置、保留项和验收记录仅供历史追溯，不代表当前启用。详见[全部新增资源移除记录](ALL_ADDED_RESOURCES_REMOVAL.md)。

2026-10-18，v0.12.77 / revision 53。

以原版现代双侧道路停靠点`::/stations/street/small_stops/small_new_twosided.con`为底版，新增独立资源：

`tnj_tf3_ai_bridge::/stations/street/small_stops/small_new_twosided_zero_emission.con`

配置位于`mod/tf3_mcp_bridge/content/stations/street/small_stops/small_new_twosided_zero_emission.con.lua`，使用同目录独立脚本`small_stops_zero_emission.script.lua`。脚本生成的`edgeObjectEmissionEmitter.noise`与`pollution`均为0，菜单属性也标记为0；原版共用脚本和停靠点未修改。

- 保留原版现代双侧外观、1980年起可用、道路建筑菜单及客货分类。
- 保留160米覆盖半径、原版容量50和双侧对称终端配置。
- 保留客运与货物卸载功能；`cargoLoad=false`、`cargoUnload=true`，没有增加货物装载能力。
- 保留原版造价、维护费、装卸速度、道路吸附及距路口限制。
- 图标、模型、界面脚本和音效使用已核对存在的原版绝对资源引用。选择与施工音效保留，零噪音指模拟排放参数。
- 设施自身零排放不改变停靠车辆或道路的污染及噪音。

源码及本地staging已同步；模组外备份、接收器设置及mod.io绑定保留。完整配置比较和两组生成结果比较通过，生成结果相对原版仅排放参数改变；6个原版直接资源引用、48项Lua编译检查及`check_mod_package.py --require-receiver`通过。

未重载、建造、恢复监控或上传。原生校验、菜单显示、建成实体和游戏中的排放效果仍待验收，不把离线结果当作实际加载证据。当前MCP建造入口是否支持选择此新增变体未作实机验证。

本地备份与验证：`output/zero_emission_stop_20261018/`。
