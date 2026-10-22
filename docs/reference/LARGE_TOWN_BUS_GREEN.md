# 绿色大型城市公交专用道

> 2026-10-20：本文为历史记录。对应加强道路/强化车辆已从当前模组移除，见[移除范围与备份](ENHANCED_ROADS_VEHICLES_REMOVAL.md)。


## 当前核对（v0.12.76 / revision 52，2026-10-18）

与强化小型、中型城市道路统一核对为绿色路面、800 km/h机动车道限速。本模板及样式原本已满足，内容未改；每方向最外侧仍允许BUS/TRUCK、禁止CAR，其他车道、步行速度、宽度、费用及资源ID不变。源码与staging的配置、green_paving/green_lane材质引用和绿色着色值通过Lua执行检查；桥接24项编译检查及`check_mod_package.py --require-receiver`通过，接收器设置与mod.io绑定保留。未重载、施工或上传，游戏画面及实际效果待验收。备份及验证见`output/town_roads_green800_20261018/`。

## 初始版本记录

2026-10-18，v0.12.74 / revision 50。

- 名称：大型城市道路（绿色公交专用道 · 800 km/h）。
- 模板：`tnj_tf3_ai_bridge::/roads/town_large_bus_800_green.street_template`。
- 样式：`tnj_tf3_ai_bridge::/roads/town_large_green.street`。

复制原版`street/town/town_new_large_bus.street_template.lua`，只改名称、样式和六条机动车道速度（800/3.6 m/s）。双向各三条机动车道，每方向最外侧为原生公交道，允许BUS/TRUCK，禁止CAR；不是仅允许公交车。两侧人行道速度、宽度、费用、年代及菜单分类沿用原版。

样式复制原版大型城市道路，将相对资源引用解析为原版绝对命名空间。行车道、基础铺装及路口采用现有绿色材质；保留公交标线、车道线、人行道、路灯、消防栓、垃圾桶和电车相关配置。

已备份并同步源码和本地staging，版本同步且接收器、mod.io绑定保留。Lua执行、模板完整结构差异、公交标线引用、两份新增文件一致性以及`check_mod_package.py --require-receiver`通过。未重载、施工、上传或进行游戏内画面/行车验收。限速不代表车辆必然达到该速度。

本地备份及验证：`output/town_large_bus_green_800_20261018/`。
