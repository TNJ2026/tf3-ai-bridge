# 世界操作接口（worldActionsVersion=1）

> 用户范围调整（2026-10-17）：城市分布权重暂时忽略，不作为本轮验证完成条件，不记为已通过；声音、视觉效果和过场同样暂时忽略。其余未完成项按[验证台账](../../output/api_all_20261017/RESULT.md)保留。本次仅更新范围，不部署或操作游戏。

> 全目录验证台账（2026-10-17）：已在授权测试副本执行广泛写入，修复城市快照、自定义状态参数、库存及模型实例嵌套序列化，加载0.12.71/revision47；原存档已读回恢复，保留两辆在线车辆并恢复1倍速。47项逐项区分字段验证、仅原生接受、原生拒绝、设计阻断及缺少目标，**并非全部通过**。城市分布字段及部分目标发现/效果验收仍有阻碍。见[完整台账](../../output/api_all_20261017/RESULT.md)。

> 往返写入验收（2026-10-17）：产业产量倍率、产业手动发展、建筑保护、时刻、云量、日期6类操作共12次提交全部独立读回verified=true，均已恢复原值并恢复2倍速，无pending。实际发车/掉头及GUI效果仍待验证，城市快照问题未修复。见[实测记录](../../output/api_roundtrip_tests_20261017/RESULT.md)。

> 购车写入实测（2026-10-17）：用户授权仅本次无费用测试，购入1辆强化GAZ 3307（27144），手动发车开关完成开启与恢复，两次均callback=true、独立读回verified=true。新车留在Masham车库，恢复2倍速、无pending；未提交掉头或实际发车。见[购车测试记录](../../output/api_purchase_test_20261017/RESULT.md)。

> 车辆补测（2026-10-17）：车辆18502的手动发车开关和掉头预览通过，未提交；途中立即发车被AT_TERMINAL前置限制正确拒绝。用户授权的临时暂停已结束并恢复2倍速，无pending。见[车辆测试记录](../../output/api_vehicle_tests_20261017/RESULT.md)。

> 后续预览验收：建筑保护、产业倍率/手动发展、日期、时刻、云量6项通过；创建城市按设计阻断。城市发展开关预览受共享TOWN快照中不可序列化分布权重字段阻碍，尚未修复。当前无车辆/线路，相关实测未执行。详见[后续测试](../../output/api_additional_tests_20261017/RESULT.md)。

> 最新实机验收（2026-10-17，v0.12.68）：calendar_speed完成4000→5000→4000毫秒/天的预览、独立备份、单次提交和独立读回，两次均verified=true；日期和gameTime不变，恢复原值并保持本次重载时的暂停状态，接收器ready且无pending。其他写适配器未因此视为全部验收。见[闭环证据](../../output/api_live_v68_20261017/RESULT.md)。

> 2026-10-17 写入复验：备份和预览通过，提交因暂停时tickCount增长导致指纹失配而在执行前被拒绝，日历速度未修改，已恢复1倍速。v0.12.68/revision44排除该内部计数但保留真实状态检查，78项专项通过；已部署，等待重载后完成写入闭环。见[测试记录](../../output/api_calendar_fix_20261017/RESULT.md)。

> 最新实机结果（2026-10-17，v0.12.67）：30项扩展能力、47项世界动作原生入口全部识别；世界动作保留39项开放/8项阻断。镜头、过场、性能、列车阻塞及环境采样只读调用通过，语音播放状态可读、空资源保留缺失标记。接收器ready、pending为空。GUI效果及世界写操作未执行，不能扩展为全部接口效果验收。见[逐项实机记录](../../output/api_live_v67_20261017/RESULT.md)。

> 最新状态：v0.12.66 实机已验证世界操作模块可加载并返回47项目录，接收器保持 ready、无pending。诊断确认原生函数实际为table，旧函数类型检查误报不可用；v0.12.67 / revision43 已改用项目既有原生绑定兼容检查，213项专项与编译/包校验通过，等待再次载入地图验收。见[复验记录](../../output/api_live_v66_20261017/RESULT.md)。

> 修复进展：0.12.66 / revision 42 已部署，完整资源路径、固定原生 API 引用及预检错误回执已修复；离线回归/编译/包校验通过，等待重新载入地图验收。原失败请求已按固定源码和日志证据记录为引擎分发前拒绝，未重发。见[修复记录](../../output/api_fix_20261017_211817/RESULT.md)。

> 2026-10-17 实机验证未通过：能力查询返回29项不可用；世界动作目录因模块加载失败使接收器停止。仅连接、地图身份及能力目录读取通过，未进行世界写入。详见[实机验证记录](../../output/api_live_20261017/RESULT.md)。以下离线实现/部署状态不代表实机可用。

2026-10-17：新增世界操作目录与统一预览、备份、单次提交、独立读回通道，覆盖此前遗漏的产业、车辆、城市建筑、日期环境、库存和自定义实体命令。**47项纳入目录，39项有执行适配器，8项仍阻断提交**，具体限制见下表。不能将目录覆盖说成全部命令可执行。

2026-10-17 已部署到本地 staging，版本 0.12.65 / revision 41，包校验和六种 Lua 运行时编译通过。MCP 使用当前源码，新进程导入注册通过；现有 MCP 进程尚未重连，游戏心跳过期，未重载游戏或修改当前地图。原生模组校验及实机接口验收仍待完成。离线测试不代表原生游戏中全部命令已验收。保留既有车辆属性与外观接口，不重复覆盖其来源合成逻辑。

## 统一MCP入口

| 工具 | 用途 |
|---|---|
| `list_world_actions()` | 返回逐项原生命令、参数类型、函数可用性、适配器状态及阻断原因 |
| `preview_world_action(action, parameters)` | 校验参数、暂停、实体与前置状态，返回当前值、目标值和60秒一次性令牌；不调用原生写命令 |
| `commit_world_action(preview_token)` | 公共工作流锁内创建已验证独立备份，再提交一次；随后调用独立读回 |
| `get_world_action_operation(operation_id)` | 只读原操作回执和当前状态，不重新提交 |

动作与参数采用固定目录白名单。不存在传入任意原生方法、组件路径、Lua代码或命令对象的入口。参数类型和适配器限制可通过目录发现；省略、额外参数、非有限数和路径穿越均拒绝。直接底层提交必须提供当前会话/代际120秒内未被修改的已验证备份，填写任意文件名不能绕过。

示例（先确认用户已授权具体修改）：

```python
preview_world_action(action="industry_productivity", parameters={"entity": 农场产业ID, "productivity": 5})
preview_world_action(action="vehicle_manual_departure", parameters={"entity": 车辆ID, "manual": True})
preview_world_action(action="building_protection", parameters={"entity": 城市建筑ID, "blocked": True})
preview_world_action(action="calendar_speed", parameters={"millis_per_day": 4000})
preview_world_action(action="game_date", parameters={"year": 2000, "month": 2, "day": 29})
# 根据返回的具体预览提交；令牌不是批量任务，也不恢复监控。
commit_world_action(preview_token="返回的preview_token")
```

## 已实现动作

| 分类 | action | 语义与限制 |
|---|---|---|
| 产业 | `industry_productivity` | 调用StockList倍率命令；目标使用产业ID，读回真实关联库存的productivity。设置绝对倍率，不是对已有倍率再乘；不修改库存容量，可能被游戏后续加成重算覆盖 |
| 产业 | `industry_manual_development`, `industry_closure_time` | 手动发展开关、原生关闭时间戳；不是年/月/日 |
| 产业扩建 | `industry_extend` | 调用生成扩建Proposal的命令，返回提案及碰撞子结构信息；**只生成，不施工、不提供完整费用/碰撞验收**。不得把返回结果当作已扩建 |
| 车辆 | `vehicle_manual_departure`, `vehicle_depart`, `vehicle_reverse` | 当前玩家车辆；立即发车只允许当前AT_TERMINAL。暂停下提交命令不证明车辆已实际驶离 |
| 城市 | `town_development`, `town_initial_capacities`, `town_size`, `town_distribution` | 自动发展、三类初始容量、规模倍率、3×4分布权重。`town_size.update_buildings`仅支持false；立即生成/升级建筑需要施工适配器 |
| 建筑 | `building_protection` | 原生城市建筑blockedDevelopment，不是普通设施的任意参数 |
| 时间环境 | `calendar_speed`, `game_date`, `time_of_day`, `cloud_coverage`, `wind` | 日历毫秒/天与游戏倍速不同；日期校验闰年；时刻秒数0～86399；云量0～1；风目标必须有EMISSION_GRID |
| 实体 | `entity_emissions`, `entity_name`, `entity_owner`, `entity_bulldozable` | 排放使用5参签名（两种功率及两种半径）；名称强制同一实体，不隐式重命名站点父对象；拆除锁必须可读，否则预检拒绝 |
| 库存 | `stock_cargo_type`, `stock_discard` | 原生库存槽ID检查，货品必须存在；丢弃会销毁货物，不是卸货/配送 |
| 自定义实体 | `custom_entity_create`, `custom_entity_destroy`, `custom_entity_state`, `custom_entity_transform` | 明确模型资源；删除/状态/变换要求CUSTOM_STATE；状态JSON最多4层、每容器32项、2048字节；变换为4列仿射矩阵。不是替换普通运输车辆 |
| 动物 | `animal_spawn`, `animal_state` | 模型须带动物元数据；状态更新暂只保持当前原生movementType，修改速度等，不猜测其他模式索引 |
| 玩家 | `add_player` | 创建游戏内玩家，不是账号注册/网络账户操作 |
| 城市连接 | `town_detect_connections` | 原生检测/更新连接关系，不建道路 |
| 日志 | `journal_clear`, `journal_log` | 清空原生日志/记入指定记录；不可作为清除pending或财务对账的替代手段 |
| 调试 | `debug_maintenance_cost`, `debug_person_happiness`, `debug_stock_amount`, `debug_simulation_steps`, `debug_clear_logbooks` | 原生debug命令，明确标识；库存数量不超当前容量；推进模拟1～100步会改变世界时间/模拟；不能由监控推断授权 |
| 调试组件 | `debug_component_exchange` | 仅复制现有`EMISSION_EMITTER`到同类型目标，使用原生新对象；不暴露任意组件写入，不支持ModelInstanceList交换 |

## 仍阻断的8项

| action | 具体阻碍 |
|---|---|
| `town_create` | TownInfo生成及原生费用/碰撞提案适配器尚未实现 |
| `town_destroy` | 会连同城市道路和建筑删除；缺少完整受影响对象与拆除预览 |
| `town_develop_at` | 原生开发器直接生成道路/建筑，缺少安全施工预览 |
| `town_connect_industries` | 自动生成/移除道路，缺少原生报价、碰撞和保护对象检查 |
| `world_replace_terrain` | 整图GameMap/Terrain转换与受影响对象预览未验证；不拿它绕过普通地形保护 |
| `custom_vehicle` | 官方目前只支持AIR、单节和特定MovePathAircraft状态；不能把普通载具路径直接复制为合法自定义飞机 |
| `journal_book_asset` | 本机声明中的JournalEntry是不透明类型，缺少已验证构造及记账语义 |
| `debug_person_state` | 只声明整数，未提供已验证状态枚举与迁移规则，拒绝随意写状态值 |

这些动作可通过目录和预检查询准确原因，**没有提交令牌，不会调用命令**。原生函数是否存在与执行适配器是否完备分开报告。

## 结果、并发和异常

- 预览是状态修改审阅，不冒充原生施工预览。预览后目标、归属或世界身份改变，提交前拒绝。暂停是所有可执行动作的前置条件；不自动暂停/恢复游戏。
- 提交前消耗令牌、持久记录操作及pending，再调用命令；超时、抛错或无布尔回调保持未知，禁止重发。新会话不能验收旧操作；额度重置会使已有预览失效，但保留操作证据。
- 读回必须在独立请求中进行。可明确比较的字段一致才`verified=true`；字段不一致保留pending。原生明确拒绝后，也必须独立确认目标快照没有变化才解除pending；部分变化保留待诊断。
- 对发车、掉头、清日志、排放双半径等尚无完整结果谓词的动作，原生成功回调加独立快照可终结为`accepted_unverified`，但**verified=false**，只证明命令被原生接受，不承诺全部效果。创建结果只验证回调实体存在；不证明运输功能、物理稳定或长期运行。
- 独立备份和所有读回证据保留；不会修改暂停的自动化、既有预算或重置未知请求。API数值边界为适配器限制，不称为游戏硬上限。

## 源码与验证

### 2026-10-17 实机补验与暂缓范围

提交前最新全量回归：`server/tests`共2202项通过（106.06秒），仅pytest缓存目录权限警告；47项Python/Lua目录一致，暂存区空白检查通过。离线回归不替代以下实机效果边界。

用户确认暂时忽略风场；此前声音、标记/高亮/驾驶舱等视觉效果、城市分布权重及过场动画同样暂缓验收。接口保留，不标为已验证。

- `debug_stock_amount` 在捕鱼场4067将工具数量从0改为10，聚合及槽位数量读回一致；质量统计仍为0，不能认定完整货物状态有效。
- `stock_discard` 原生接受后，立即及10个模拟步后的数量仍为10，本样例清除效果未通过。
- `vehicle_reverse` 原生接受并重算路径，但车辆仍沿原方向前进，实际掉头效果未通过。
- `debug_simulation_steps` 的10步使游戏时间增加2000，车辆位置改变，时间推进效果已确认。
- 车库23760缺少`BULLDOZER_INFO`，拆除锁预检阻断；排放及组件交换缺少有效目标发现，日志缺少完整内容读回，仍待验证。
- `get_stock_cargo` 不在批量白名单内，应走独立查询；本轮混合批量在客户端拒绝，未发送原生请求，不代表游戏端错误。

测试后已读回测试前存档，独立确认工具数量恢复0、车辆位置/路径及线路恢复，恢复原1倍速。完整本地证据在`output/api_all_20261017/REMAINING_VERIFICATION.md`与`remaining_verification.json`（运行证据不纳入Git）。

- `server/src/tf3_mcp/world_commands.py`：47项目录、主机校验和MCP入口。
- `mod/tf3_mcp_bridge/content/tf3_mcp_bridge/world_actions.lua`：原生构造、预览、单次分发及读回；由桥接按需加载。
- `scripts/sync_world_action_catalog.py`：默认检查Python/Lua目录一致性，`--write`原子更新嵌入目录。
- `server/tests/test_world_commands.py`：真实桥接Lua与模拟原生API。覆盖全部目录入口、提交回调、延迟/未知/状态不符、陈旧令牌、旧接收器阻断和备份顺序；不等于实机验收。

本次验证：专项73项、全量`server/tests`共2153项通过（93.24秒）；全量运行需将`server/src`和`scripts`加入`PYTHONPATH`。Lua 5.1/5.2/5.3/5.4、LuaJIT 2.0/2.1均在额外预留16个局部变量条件下编译通过；MCP注册表包含全部4个统一入口，Python/Lua动作目录一致，源码空白检查通过。

依据为本机游戏`api/tealdef/api/cmd.d.tl`、`engine.d.tl`与`type.d.tl`。在线参考：[命令API](https://wiki.transportfever3.com/script-doc/api/cmd.html)。
