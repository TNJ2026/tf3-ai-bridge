# 直升机场3000米维护半径

当前状态（2026-10-22，v0.12.119 / revision95）：已按用户要求撤销全部道路及附加资源属性覆盖，并从源码和 staging 移除全部新增道路、车辆、直升机与设施。本页以下配置、保留项和验收记录仅供历史追溯，不代表当前启用。详见[全部新增资源移除记录](ALL_ADDED_RESOURCES_REMOVAL.md)。

2026-10-19补充：另有[独立8架同时维护、3000米半径的直升机场副本](HELIPORT_8_3000.md)。本页原版资源修改仍保持4架同时维护，不因新增副本改变。

2026-10-18，v0.12.78 / revision 54。

启用本模组后，原版直升机场`::/stations/air/heliport.con`的购机机库维护半径由800米改为3000米（直径6000米）。保留原资源ID和原生生成脚本，不新增另一种直升机场，不改写基础游戏安装文件。

实现位于现有模组入口`content/farm_balance.script.lua`：注册精确匹配`::/stations/air/heliport/heliport.script`的`loadScript`修改器，保留原生`updateFn`并在其返回后只改机库`depot.catchmentArea.radius`。对同一脚本对象不重复包装；原生机库布局不可识别时明确拒绝，避免将客货覆盖当作维护范围。保留原有农场调整逻辑。

同时维护数量仍为4，购机停放容量仍为5，客货接收覆盖半径仍为175米。费用、模块、几何、通行模式、噪音和污染均不变；小型停机坪、飞机场及其他维护设施不在本次范围内。

桥接`build_heliport`预览能力说明及`commit_facility`独立读回要求同步为3000米；实测机库半径仍为800米时不能通过服务验收。配置更新不代表当前地图已经加载，也不能保证既有设施重载后立即重算。

源码和本地staging已同步，修改前文件已在模组外备份；接收器设置和mod.io绑定保留。20项相关测试、48项Lua编译检查及`check_mod_package.py --require-receiver`通过。对本机原生完整直升机场脚本进行离线执行比较（美术与几何工具依赖使用模拟对象），生成结果只有维护半径发生变化，终结回调和其他配置保留。

未重载、施工、恢复监控或上传。原生校验、当前设施刷新、实际维修及长期模拟效果尚未验收。备份及证据：`output/heliport_maintenance3000_20261018/`。

修改器依据：[官方资源修改器说明](https://wiki.transportfever3.com/doku.php?id=modding:scripting:modifiersfilters)列出`loadScript`；本机`base/content/base.zip`内`base/mod.lua`也注册此类别。官方页面标记部分内容尚未适配TF3，因此具体原生字段以本机`stations/air.zip`内的直升机场脚本和离线执行为依据。
