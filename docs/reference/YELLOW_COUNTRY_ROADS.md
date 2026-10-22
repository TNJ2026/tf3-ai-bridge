# 黄色小型乡村公路

> 2026-10-20：本文为早期独立黄色道路的历史记录，移除事件见[移除范围与备份](ENHANCED_ROADS_VEHICLES_REMOVAL.md)。后续按用户要求，仅恢复本次中型道路需要的黄色样式/材质与兼容模板，并已在v0.12.94直接修改内置中型乡村道路。当前名称、限速、实现和实机边界以[内置中型乡村道路](MEDIUM_COUNTRY_800_YELLOW.md)为准；小型、大型等其他旧道路未随之恢复。


## 大型乡村公路隔音栏版（v0.12.72 / revision 48）

后续更新（v0.12.73 / revision 49）：按用户要求将同一资源改为黄色路面，复用`country_wide_yellow.street`及黄色材质，名称更新为“大型乡村公路（黄色隔音栏版 · 800 km/h）”。六条机动车道限速、双侧原生隔音栏及其他配置保持。已同步本地staging，Lua/完整结构差异和接收器目录校验通过；尚未重载或游戏内画面验收。备份：`output/country_large_barriers_yellow_20261018/`。下文原版路面为初建版本记录。

2026-10-18新增独立资源`tnj_tf3_ai_bridge::/roads/country_large_barriers_800.street_template`，菜单名称“大型乡村公路（隔音栏 · 800 km/h）”。复制原版`country_new_large_barriers.street_template.lua`，只修改名称和六条机动车道速度（800/3.6 m/s）。双向各三车道，保留原版路面、两侧通行带、费用、年代和菜单分类；本版本不是黄色路面。

保留两侧`::/infrastructure/edge_addons/barrier_b.edge`原生隔音栏，装饰自身配置`noiseModifier=-0.65`；不叠加到道路修改器，也不据此宣称实测城市噪音下降65%。原生栏杆的桥隧、路口及地块兼容性沿用原版。

已同步源码和本地staging，独立保留接收器与mod.io绑定，备份位于`output/country_large_barriers_800_20261018/`。Lua执行、完整结构差异检查及`check_mod_package.py --require-receiver`通过。未重载、上传、施工或进行游戏原生菜单/画面验收；重载模组后可检查新增条目。

## 中型与大型扩展（v0.12.45 / revision 21）

2026-10-17新增两条800 km/h黄色乡村公路：

- `tnj_tf3_ai_bridge::/roads/country_medium_800_yellow.street_template`：中型，双向各2机动车道，宽度2/5/4/4/5/2米。
- `tnj_tf3_ai_bridge::/roads/country_large_800_yellow.street_template`：大型，双向各3机动车道，宽度2/5/4/4/4/4/5/2米。

分别复制原版对应规格模板，保留原宽度、费用、菜单、可用年代、侧道及simBuildable设置。仅名称、样式和4/6条机动车道速度改变。共享新建 `country_wide_yellow.street.lua`，基于原版两种规格使用的 `country_new_large.street` 样式，复用既有黄色路面材质。

Lua及完整模板结构差异检查通过，源码与本地staging同步并备份。尚未重载、地图施工或原生画面/行车验收。备份：`output/country_wide_800_20261017_142637/`。

## 小型版本

2026-10-17，v0.12.43 / revision 19。按用户要求生成三条独立道路，基于原版 `country_new_small.street_template.lua`：

| 名称 | 资源（前缀均为 `tnj_tf3_ai_bridge::/roads/`） |
|---|---|
| 小型乡村公路（黄色 · 300 km/h） | `country_small_300_yellow.street_template` |
| 小型乡村公路（黄色 · 500 km/h） | `country_small_500_yellow.street_template` |
| 小型乡村公路（黄色 · 800 km/h） | `country_small_800_yellow.street_template` |

机动车道速度分别为300/3.6、500/3.6、800/3.6 m/s。保留原版双向各一条机动车道、两侧通行带，宽度2/5/5/2米；费用、1940年可用、乡村道路分类及simBuildable=true不变。完整Lua结构比较确认模板仅名称、样式和两条机动车道速度不同。侧道速度保持原值。

三条道路共享独立 `country_small_yellow.street.lua` 样式，以及 `mat/country_yellow_paving.mtl`、`mat/country_yellow_lane.mtl` 两份材质。行车道、基础铺装及路口采用黄色着色系数 `{1,0.85,0.06}`，保留原版贴图细节、透明及法线配置，标线和路缘保持。8个直接纹理引用已核对原版归档存在。原版道路、既有绿色城市街道不受影响。

已同步源码及本地staging、在模组外备份，Lua解析及逐文件一致性检查通过。尚未重载、原生菜单/画面验收或建造；实际颜色受光照影响，车辆实际速度仍受动力、弯道和交通限制。保留自动建设资格不等于已自动建造。

备份及验证：`output/country_yellow_20261017_141359/`。
