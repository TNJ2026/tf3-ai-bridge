# 载具属性修改接口

2026-10-17：v0.12.34 / revision 10 已部署并原生加载，要求接收器 `vehicleModifiersVersion=1`。Citaro G1 单车速度倍率1→10已提交并独立核对来源与有效值；其他三项仍为1。未测试装载速度修改、实际达到理论速度、跨存档持久性及长期模拟。旧版接收器会在发布请求前拒绝调用。

现场证据：[Citaro 测试记录](../../output/citaro_test_20261017_115250/RESULT.md)。装载速度模型值为 `loadSpeed=3`；实际 `config.loadSpeeds` 在本次原生读取中不可用，未确认独立单车 setter 或最大值，不纳入四项倍率接口。

## 本次接口

| 接口 | 用途 |
|---|---|
| `get_vehicle_modifiers(vehicle)` | 读取四项实际倍率、各修正来源、桥接自身来源及一致性 |
| `preview_vehicle_modifiers(vehicle, top_speed?, noise?, pollution?, comfort?, reset=False)` | 计算修改前后结果，生成60秒单次令牌；不是建造报价预览 |
| `commit_vehicle_modifiers(preview_token)` | 锁定工作流、验证接收器、保存并验证备份、单次提交，再独立核对 |
| `get_vehicle_modifier_operation(operation_id)` | 核对原操作，来源与实际倍率一致才解除 pending；不重发 |

四个参数都是倍率，`1` 表示中性；`top_speed` 不是 km/h。仅影响指定的整辆运输载具（包括其编组），不修改模型资源。桥接策略范围：速度 `(0,10]`，其他三项 `[0,10]`，合成结果同样检查；这些范围是本接口限制，不宣称是游戏公布的最大值。

预览和提交要求暂停游戏、载具属于当前玩家、原生修正来源和实际倍率一致。未提供的字段保留本桥接原值；`reset=True` 与倍率参数互斥，只移除桥接来源，不清除地标等来源。

```python
get_vehicle_modifiers(vehicle=实际载具ID)
preview_vehicle_modifiers(vehicle=实际载具ID, top_speed=1.5, noise=0.8)
# 检查返回的 before、desired、expected，再使用真实令牌：
commit_vehicle_modifiers(preview_token="预览返回的令牌")
# verified=false 时，只读取原 operation_id；禁止再次提交。
get_vehicle_modifier_operation(operation_id="原操作ID")
# 恢复本桥接修改也先预览，再提交：
preview_vehicle_modifiers(vehicle=实际载具ID, reset=True)
```

调用 `commit` 会自动创建独立存档备份。底层通道要求当前会话、当前代际、120秒内且文件未改变的已验证备份；仅填写文件名不构成备份证据。预览过期、车辆配置或来源改变时拒绝提交，令牌不可重复使用。

## 原生语义与验收

根据随游戏附带的 `base/content/vehicle/vehicle_modifier.script.tl` 和地标调用代码，发送 `VehicleModifier / ChangeModifier` 事件，固定来源为 `tnj_tf3_ai_bridge.vehicle_modifiers`。游戏自行维护来源表并调用 `makeVehicleSetModifiersCmd`；桥接不直接覆盖最终四项倍率，也不写组件内存。

合成公式为 `最终倍率 = 1 + Σ(各来源倍率 - 1)`。例如地标速度 `1.2` 加桥接 `1.5`，最终为 `1.7`，不是 `1.8`。无其他来源时，基础最高速度80 km/h、桥接1.5对应理论上限120 km/h；道路限速、动力、坡度等仍可能降低实际速度。噪音倍率不是直接对分贝数字乘算。

事件回执不等于嵌套命令已生效。提交保留 pending；独立读取同时核对桥接来源、其他来源未变、实际四项倍率、车辆配置及归属。丢失或异常回执、只更新来源但实际倍率未变、并发其他来源变化都不能冒称成功；保留证据，不自动重发或清 pending。来源状态不可读时拒绝写入；新存档尚无来源表但脚本状态可读时按空来源表读取，并核对实际中性倍率。

`verified=true` 表示上述静态读回一致，不证明实际最高行驶速度、长期模拟、换车后的继承或存档重载行为。游戏自身保存在 GameScript 状态中的来源预计随存档保存，仍需实机存档/重载验收。

## 还可修改哪些属性

| 属性 | 已确认入口 | 当前状态与边界 |
|---|---|---|
| 最高速度、噪音、污染、舒适度倍率 | `TransportVehicle.Modifiers` 的四个 scale 字段 | 本次封装；待实机验收 |
| 颜色、同组涂装模型 | `makeEntitySetColorCmd` / `makeVehicleReplaceCmd` | 既有外观接口；换模型受兼容性与费用检查 |
| 名称、线路、停驶、回库、行驶方向、手动发车 | 原生 Entity/Vehicle 命令 | 原生命令存在；不代表每项都有 MCP 封装，且不是机械性能倍率 |
| 陆上载具基础最高速度、功率、牵引力、空重、满载附加重量、摩擦、制动减速度 | 模型 `metadata.landVehicle` | 模型资源修改；本次不提供运行时单车 setter |
| 船舶功率、阻力截面积、基础速度、重量 | 模型 `metadata.waterVehicle` | 模型资源修改；功率单位W，与陆上kW不同 |
| 飞机推力、达到全推力时间、基础速度、重量、机翼面积 | 模型 `metadata.airVehicle` | 模型资源修改；需按车型与机场规则验证 |
| 维护费用 | `makeMaintenanceCostUpdateCmd` | API明确标记 debug；对象是维护费用实体，不能直接假设载具ID可用，本次未封装 |
| 实体排放功率/半径 | `makeEntitySetEmissionsCmd` | 原生命令存在，但适用实体、车辆重新计算覆盖关系待验证；本次采用载具倍率 |
| 容量、货品兼容、装卸速度、年龄/维护状态 | 资源/配置或模拟派生字段 | 不能因为组件可读就认为可直接写；未确认独立安全 setter，本次未封装 |

修改基础模型会影响引用该模型的载具，通常需要资源重新加载；不能承诺热更新或仅改变一辆车。容量、货品兼容、重量、站台和维护约束需要一起验证，不能靠修改显示字段冒充生效。

## 依据与测试

- [官方 Engine API](https://wiki.transportfever3.com/script-doc/api/engine.html)：`TransportVehicle.Modifiers`、只读引擎组件。
- [官方 Vehicle Types](https://wiki.transportfever3.com/doku.php?id=modding:vehicles:types)：陆上、水上、航空模型字段与单位。
- 本机官方游戏：`api/tealdef/api/cmd.d.tl`、`base/content/vehicle/vehicle_modifier.script.tl`、`base/content/landmarks/landmarks.script.tl`；2026-10-17核对。
- `server/tests/test_vehicle_modifiers.py`：原生 API 模拟覆盖来源保留、部分更新、重置、延迟/未知结果、来源与实际值不一致、所有权、暂停、会话、令牌消费、范围、备份和旧接收器拒绝。
- Lua六种运行时各做普通编译与预留16个局部变量编译；不是游戏原生加载验收。
