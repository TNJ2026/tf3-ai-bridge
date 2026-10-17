# 普通农场产量与库存调整

2026-10-17，0.12.48 / revision 24。用户要求产量变为原来的5倍，库存容量变为原来的10倍。

入口为 `mod/tf3_mcp_bridge/content/farm_balance.script.lua`，由本地 `mod.json` 的 `runScript` 注册 `loadConstruction` 修饰器，只匹配 `::/industries/farm/farm.con`。保留原版资源身份，不创建新农场类型；棉花农场、橡胶农场、畜牧场及其他模组资源不受影响。

| 配置 | 原版 | 调整后 |
|---|---:|---:|
| 每次生产规则的蔬菜产出 | 16 | 80 |
| 每次生产规则的谷物产出 | 24 | 120 |
| 肥料库存容量 | 100 | 1000 |
| 蔬菜库存容量 | 200 | 2000 |
| 谷物库存容量 | 300 | 3000 |

非 booster 规则的 output 乘5，stocks.capacity 乘10。生产规则频率、等级、肥料消耗及加成规则、工人配置和外观保持原值。实际年产量仍受等级、生产状态、加成、库存和运输等影响；不是历史产量立即乘5，也不向库存凭空添加货物。其他模组若先调整同一原版配置，则倍率作用于收到的配置。

## 已有存档与验收边界

原生 `industryutil.lua` 会优先读取建筑参数 `params.output`、`params.stocks` 等覆盖值，再使用资源配置。本次只修改加载阶段的资源配置，没有修改地图实体或绕过原生建造接口。已有农场是否在读档时重算，及其是否持有参数覆盖，必须逐项读取确认；不能以资源文件更新代替存档生效验收。若仍为旧值，继续调查受支持的原生更新流程，先备份及预览，不直接删除重建农场。

本次 MCP 心跳过期，无法完成现场验收。已同步源码与 staging；未重载、上传、建造或恢复监控。接收器配置及线上绑定保留。离线执行原版 farm.con.lua（仅桩替代 makeIndustryParams）后应用修饰器，数值、保留项、重复回调及非目标排除通过；发布目录检查42文件、无问题。没有完成游戏原生加载及校验。

证据与备份：`output/farm_balance_20261017_183938/`。

依据：[官方模组脚本入口](https://wiki.transportfever3.com/doku.php?id=modding:general:modscripts)。[资源修饰器页](https://wiki.transportfever3.com/doku.php?id=modding:scripting:modifiersfilters)标注尚未适配TF3，因此另外核对本机 base.zip 的 `base/mod.lua`、`base/base_mod.lua`：当前游戏注册并调用 `loadConstruction`，原生自身亦使用该入口修改 stockListConfig。
