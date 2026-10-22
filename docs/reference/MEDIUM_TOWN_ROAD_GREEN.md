# 绿色中型城市道路

> 2026-10-20：本文为历史记录。对应加强道路/强化车辆已从当前模组移除，见[移除范围与备份](ENHANCED_ROADS_VEHICLES_REMOVAL.md)。


## 当前配置（v0.12.76 / revision 52，2026-10-18）

四条机动车道限速统一提高到800 km/h，显示名称为“中型城市道路（绿色 · 800 km/h）”。保留既有green_paving/green_lane绿色材质，以及原资源ID `tnj_tf3_ai_bridge::/roads/town_medium_800.street_template` 和样式ID `tnj_tf3_ai_bridge::/roads/town_medium_500_green.street`。样式文件名中的500不代表当前限速；车道数量、通行模式、宽度、步行速度、费用及其他配置不变。

源码与本地staging已更新并在模组外备份；Lua执行与完整结构比较、桥接24项编译检查及`check_mod_package.py --require-receiver`通过，接收器设置和mod.io绑定保留。未重载、施工或上传，实际画面与既有道路生效情况待游戏内验收。备份及验证见`output/town_roads_green800_20261018/`。

## 历史配置（v0.12.60）

2026-10-17，0.12.60 / revision36。原加强版中型城市道路四条机动车道由800改为500km/h；名称改为“中型城市道路（绿色 · 500 km/h）”。保留 `tnj_tf3_ai_bridge::/roads/town_medium_800.street_template` 资源ID，避免破坏存档引用。

独立样式 `content/roads/town_medium_500_green.street.lua` 从原版town_new_large.street复制，保留原有路缘、人行道、标线与沿街设施。streetPaving、streetLane、crossingLane使用已有green_paving/green_lane材质；所有原版美术引用规范化。车道数量、宽度、两侧步行速度13.89、费用与其他道路属性不变。

源码与staging同步，Lua执行验证四机动车道500/3.6及人行道原速、样式材质引用。包检查69文件无问题；版本及接收器/绑定保护完成。未重载、升级地图道路或验收视觉效果；既有路段限速及材质是否自动更新须现场检查。

证据与备份：`output/medium_road_green_20261017_193104/`。
