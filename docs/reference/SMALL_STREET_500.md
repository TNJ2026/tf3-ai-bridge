# 500 km/h小型街道

## 绿色路面（v0.12.42 / revision 18）

按用户指定改为绿色。新增独立材质 `content/roads/mat/green_paving.mtl` 与 `green_lane.mtl`，保留旧式铺装的原版纹理、透明通道、法线与反射配置，使用官方 `albedo_scale.fragmentProperties[].albedoScale={0.12,1.0,0.16}` 着色。街道样式的streetPaving、streetLane和crossingLane指向这些材质；标线、人行道、路灯和500 km/h限速保持。

材质的全部10个纹理引用已核对基础游戏归档存在，Lua解析及源码/部署一致性检查通过。已备份并同步本地staging；尚未重载或进行游戏画面验收，实际色彩受照明和纹理叠加影响。未修改基础游戏资源。

官方字段依据：https://wiki.transportfever3.com/doku.php?id=modding:general:resourcetypes:mtl#albedo_scale

## 独立路面外观（v0.12.41 / revision 17）

按用户要求，为此500 km/h小型街道新增 `content/roads/town_small_500_paving.street.lua` 独立样式。复制原版town_new样式，将所有资源引用规范化为基础游戏命名空间；将streetPaving、streetLane和crossingLane切换为原版old_town铺装材质，以旧式铺装纹理区分现代沥青。人行道、路灯、标线、消防栓、垃圾桶等保留，限速、道路宽度及费用不变。800 km/h道路和原版街道不受影响。

新旧路面材质归档条目存在，Lua解析、500限速及部署一致性检查通过；尚未重载或进行游戏画面验收。既有道路是否立即刷新需重载后核实。

## 初始版本记录

2026-10-17，v0.12.40 / revision 16。独立资源：

`tnj_tf3_ai_bridge::/roads/town_small_500.street_template`

文件：`mod/tf3_mcp_bridge/content/roads/town_small_500.street_template.lua`。

复制原版 `street/town/town_new_small.street_template.lua`，名称为“小型街道（500 km/h）”。仅修改名称与两条CAR/BUS/TRUCK车道速度，设为 `500 / 3.6` m/s。保留双向各一条机动车道、宽度3/5/5/3米、人行及CARGO侧道原速度、费用、材质、1940年起可用、菜单及simBuildable=true（因此仍具有原版自动建设资格）。不会自动替换既有道路。

Lua解析及完整结构比较确认差异仅上述三处，源码与本地staging一致，接收器配置保留。尚未重载、原生菜单验收或地图建造；限速配置不保证车辆实际达到500 km/h，其他车辆、弯道及交通限制仍适用。
