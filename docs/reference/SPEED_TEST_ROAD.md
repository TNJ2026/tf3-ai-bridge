# 独立高速测试道路

2026-10-17：v0.12.35 / revision 11 已新增资源并同步本机 staging，并按用户授权通过 MCP 备份及单次重载。原生模板查询确认新资源已加载，四条机动车道速度为222.222229 m/s（约800 km/h），两侧人行道速度仍为13.89 m/s。尚未进行菜单像素验收、Mod Hub 原生发布校验或实际铺路，现有路段未替换。

- 菜单名称：**中型城市道路（800 km/h 测试）**。
- 基础：游戏 `street.zip` 内的 `street/town/town_new_medium.street_template.lua`，普通现代中型城市道路。
- 新资源：`tnj_tf3_ai_bridge::/roads/town_medium_800.street_template`。
- 源码：[town_medium_800.street_template.lua](../../mod/tf3_mcp_bridge/content/roads/town_medium_800.street_template.lua)。
- 菜单类别沿用 `roads_medium`；可用年份沿用1940年起。

与原始模板逐字段比较，差异恰好五处：显示名称，以及四条 `CAR/BUS/TRUCK` 车道的 `speed`，由13.89 m/s改为 `800 / 3.6` m/s。两侧 `PERSON/CARGO` 车道速度不变。宽度、高度、方向、样式、基础资源引用、费用、维护、排放、通行权限及其他字段完全保留；原版模板文件未改写。

注意：按“仅修改速度”要求，`simBuildable=true` 也沿用原版；没有另外禁用模拟自动选用资格。新资源不是给已铺道路自动提速，但不能承诺自动建设系统永远不选择它。若后续要限制为仅手动建造，应单独调整此字段并验证。

桥梁限速、弯道、交叉口、拥堵和车辆动力仍可能限制实际速度。800 km/h 是本次测试设定，不是已确认的游戏最大值。当前道路升级接口缺少完整原生报价与碰撞预览，不能凭资源存在就跳过其施工约束。

验证：Lua执行解析成功；与原版结构比较只有预期五处差异；源码与部署资源字节一致；`check_mod_package.py --require-receiver` 通过。现场备份与比较证据位于 `output/speed_road_20261017_120147/`，不等于游戏原生校验。

重载证据：同目录 `reload_result.json`、`loaded_template.json`。读档时间、玩家、世界精确验收通过，无未决请求；保持重载前的暂停状态。另读取原 Citaro G1，确认速度倍率10在本次保存重载后保留，见 `vehicle_after_reload.json`；不代表实际车速或长期模拟验收。
