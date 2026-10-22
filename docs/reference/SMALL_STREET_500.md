# 内置小型街道修改与恢复记录

当前状态（2026-10-22，v0.12.119 / revision95）：已按用户要求撤销全部道路及附加资源属性覆盖，并从源码和 staging 移除全部新增道路、车辆、直升机与设施。本页以下配置、保留项和验收记录仅供历史追溯，不代表当前启用。详见[全部新增资源移除记录](ALL_ADDED_RESOURCES_REMOVAL.md)。

## 当前：恢复原版参数（v0.12.116 / revision92，2026-10-21）

用户要求还原小型街道参数。本次撤销内置 `::/infrastructure/street/town/town_new_small.street_template` 的全部本模组覆盖：500 km/h机动车道速度、绿色样式及 `speedCoeffs={300,300,300}`。将仅含此项调整的 `road_adjustments.script.lua` 在源码和staging移至模组外备份，清空 `mod.json.postRunScript.fileName`，下次资源加载使用完整原版模板，不修改游戏安装归档。

本机原版归档中两条机动车道速度为13.89 m/s（约50 km/h），样式为 `::/infrastructure/street/town/town_new.street`。原版模板未显式设置speedCoeffs，恢复为引擎原始默认行为，不将未知默认值写成0或1。独立绿色材质／样式保留以兼容可能已有存档引用，其他道路和车型保持。

源码／staging在模组外备份后同步，81种道路模板在剩余加载钩子下逐字段保持原版；Lua编译、源码目录及staging `--require-receiver` 检查通过，正式接收器和线上绑定保持。完整证据见[verification.json](../../output/town_small_restore_20261021/verification.json)。本次未保存、重载、施工、上传或恢复监控；当前游戏内存及既有道路实体可能保留原值，需用户重载后独立验收，不宣称已恢复每一段存档道路。

## 历史：speedCoeffs三个系数设为300（2026-10-21）

v0.12.115 / revision91按用户明确要求，给内置现代小型街道 `town/town_new_small` 设置 `speedCoeffs = {300,300,300}`。这是原生 `StreetTemplate.speedCoeffs : {number}` 数组中的原始值，不换算为m/s，也不将其描述为固定300 km/h路口限速。500 km/h普通机动车道速度、绿色样式及其他字段保持；不修改其他模板、车辆弯道系数或既有道路实体。

源码／staging模组外备份同步完成。24组离线场景和81种原版模板逐字段比较通过，涵盖数组写入、重复执行、失败恢复及两种样式引用形式；Lua编译、源码目录与staging `--require-receiver` 检查通过，接收器和线上绑定保持。证据见 `output/town_small_speedcoeffs_300_20261021/`。用户此前表示“我来验证”，本次未保存、重载、改建、上传或恢复监控；原生系数加载、既有路口重算及车辆实际转弯效果尚未验收。

## 绿色模板修复已原生读回（v0.12.114 / revision90）

替换旧备用写入：仅通过 `getAsTable / setAsTable` 修改资源表，写入失败时提交完整原表恢复，禁止直接给原生 `get().streetStyle` 赋字符串。资源表的字符串／数值引用均有离线检查，但本次现场日志明确 `tableStyleType=string tableStyle=town_new.street greenStyleId=31`，不能把数值类型假设当作已证实根因。

按用户明确授权保存进度并重载，v0.12.114加载日志记录setter返回nil后通过独立资源读回，随后新会话 `get_network_template` 再次确认两条机动车道约500 km/h、`streetStyle=tnj_tf3_ai_bridge::/roads/town_small_green.street`。第一次同步因账本编码读取失败，首次重载仍为旧版；该请求成功核对结束后才完成修正同步并执行第二次独立重载，未重发未知请求。第二次保存点时间、玩家、世界和地图摘要核对通过，见 `output/town_small_green_fix_20261021/fixed_load.json`。

既有道路实体保留旧样式，画面仍为黄色，未通过改建刷新。用户随后接手验证，界面输入停止；模板绿色资源引用成功不等于既有道路像素验色成功。以下v0.12.113故障保留为历史证据，不再表示当前模板写入仍失败。

## 实机故障：显示旧乡村路面（2026-10-21）

用户重载v0.12.113 / revision89后反馈路面发黄。重新绑定当前会话并通过 `get_network_template` 独立读回：两条机动车道为138.88888549805 m/s（约500 km/h），实际样式却是 `::/infrastructure/street/country/country_old.street`，没有应用专用绿色样式。原版该样式使用 `old_country_lane.mtl` 且不含现代铺装，符合用户所述黄色／泥土路面现象；尚未取得本次有效截图，不将其冒充像素验色结果。

加载日志记录道路调整脚本第83行写入 `target.streetStyle = style` 失败，错误为 `The lua object can't be cast to desired type`，随后 `restored=false`。说明此前setAsTable及备用写入／回滚流程没有保持预期样式；不能再把离线表结构检查通过视为本版原生效果通过。具体转换规则尚未查清，当前代码尚未修复。源码与staging四份目标脚本／样式／材质逐字节一致，绿色文件未引用黄色材质，排除同步遗漏及显式黄色材质绑定。

本次仅诊断与保存证据，不改模组代码、重载、施工或恢复监控。证据见[native_style_failure.json](../../output/town_small_500_green_20261021/native_style_failure.json)。以下为本版目标配置及先前离线检查，绿色生效状态以本节实机故障为准。

## 当前配置（v0.12.113 / revision89，2026-10-21）

用户要求将小型街道最大速度改为500、路面改为绿色。本次直接调整内置现代城市街道 `::/infrastructure/street/town/town_new_small.street_template`，两条 CAR/BUS/TRUCK 机动车道速度设为 `500 / 3.6` m/s；保留原版名称、两侧 PERSON/CARGO 车道速度13.89 m/s、宽度、方向、费用、年代及其他模板字段。

专用样式 `tnj_tf3_ai_bridge::/roads/town_small_green.street` 从原版 `town_new.street` 复制，仅把 streetPaving、streetLane、crossingLane 三处材质绑定到两份专用绿色材质。保留原版纹理及其他材质参数，着色比例为 `{0.12, 1.0, 0.16}`；标线、人行道、路灯、几何及共享原版样式保持。

`mod.json.postRunScript` 注册道路资源加载后的调整，脚本只有本项城市小型街道配置。乡村道路继续使用原版配置，不恢复此前小型红色／中型黄色800覆盖，也不恢复已移除的旧独立小型街道模板。调整按独立资源读回判断成功，不用setter返回真值代替验证；异常捕获、尝试恢复并记录，避免可选调整阻断加载。

源码和实际staging在模组外备份后同步，正式接收器及线上绑定保持。14组离线场景覆盖两种通行模式表示、setter返回值及备用写入、重复执行、目标缺失与布局不符；逐字段对照81种原版模板，确认仅目标两处速度和样式变化。样式／材质对照、7份纹理引用、Lua编译、源码目录及staging `--require-receiver` 检查通过。证据与一次性执行器位于 `output/town_small_500_green_20261021/`，完整结果见[verification.json](../../output/town_small_500_green_20261021/verification.json)。

修改前实时只读确认内置小型街道为约50 km/h、原版样式，当前游戏连接正常且无pending。**本次未重载、保存、施工、上传或恢复监控。** 重新加载启用本地模组的存档后才执行新配置；500限速的原生读回、绿色像素外观、既有道路实体刷新和实际行车尚未验收。模板限速不代表所有车辆都能达到500 km/h。

## 历史：独立绿色小型街道（v0.12.76 / revision52，2026-10-18）

以下为已移除独立道路的历史记录，见[移除范围与备份](ENHANCED_ROADS_VEHICLES_REMOVAL.md)，不代表当前内置街道配置。

两条机动车道限速统一提高到800 km/h，显示名称为“小型街道（绿色 · 800 km/h）”。保留已有绿色路面：streetPaving使用green_paving，streetLane和crossingLane使用green_lane，着色比例为`{0.12, 1.0, 0.16}`。原资源ID `tnj_tf3_ai_bridge::/roads/town_small_500.street_template` 与样式文件名保留，以兼容存档引用；文件名中的500不再代表当前限速。车道数量、通行模式、步行侧道速度、宽度、费用、年代及其他配置不变。

源码与本地staging已更新并在模组外备份；Lua执行检查与完整结构比较通过，桥接24项编译检查及`check_mod_package.py --require-receiver`通过，接收器设置和mod.io绑定保留。未重载、施工或上传，实际画面与既有道路生效情况待游戏内验收。备份及验证见`output/town_roads_green800_20261018/`。以下为历史记录。

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
