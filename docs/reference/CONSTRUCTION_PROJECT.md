# 接收器工程批处理 v2

实现版本：桥接源码 `0.12.29`，能力标记 `projectBatchVersion=2`。2026-10-16 已部署、重载并完成公路公交实测：一个工程创建两条线路、采购四辆车、分配运行、跨帧确认实际出库、自动恢复暂停，返回 `complete=true`。修复了更新帧禁止命令回调导致收尾失败的问题，观察由更新帧发出无回调事件，在事件处理器完成采样和变速。原生报价、无限资金显式授权、逐项回执仍保留。实测范围及证据见 [测试记录](../../output/project_v2_live_20261016/RESULT.md)。新版发送器拒绝 v1 接收器；本次公路样例不证明其他运输方式或所有道路/设施组合均已实测。

## 执行过程

`execute_project` 在公共工作流锁内检查暂停、会话和未决状态，验证一次备份，再向接收器发送一个完整工程。接收器按顺序执行每步的原生预览、预算与碰撞检查、单次提交、原有建造读回及额外验收查询。下一步使用前一步实际返回的实体 ID。不是客户端反复发送每步施工命令。

整个工程不是原子事务：已经完成的工程会保留，后续失败不自动拆除或回滚。每步仍使用原有接口的有效预览令牌、实体保护和 pending 保护。

v2 将建线路、装载配置、批量购车、批量分配和实际投运纳入同一个工程。建线/购车使用配置、终端或原生价格预检，不冒称它们是道路施工碰撞预览。投运阶段由接收器在后续游戏更新帧继续观察；调用返回 `observing` 后只需读取进度，不需要客户端逐辆推进。

## 工具

| 工具 | 用途 |
|---|---|
| `execute_project(project_id, steps, cash_floor=5000000, reserved_cash=0, allow_no_costs=False)` | 新建并执行工程；自动生成并验证一次备份 |
| `get_project(project_id)` | 读取进度、子请求 ID、逐辆采购/分配记录、报价、验收字段及失败原因，不执行建设 |
| `resume_project(project_id)` | 新备份后继续同会话的已知阻塞、验收失败或主动让出的工程 |
| `cancel_project(project_id)` | 取消剩余工作；不回滚已建内容，不能清除未知写入 |

`project_id` 使用新生成的 32 位小写十六进制 UUID。重用已存在 ID 不会重新施工。底层 execute/resume 信封还包含由包装层生成的 `backup_save`，no_gui 发送器核实其当前会话备份记录。

每个步骤包含：

```json
{
  "id": "road1",
  "preview": "preview_road_graph",
  "arguments": {
    "graph": {
      "nodes": [
        {"position": {"x": 700, "y": 700, "z": 2}},
        {"position": {"x": 800, "y": 700, "z": 2}}
      ],
      "edges": [{"from": 0, "to": 1, "template": "town/town_old_small"}]
    }
  },
  "max_cost": 100000,
  "checks": [{
    "command": "get_entity",
    "arguments": {"id": {"$ref": "road1.commit.edges.1"}},
    "expect": {"id": {"$ref": "road1.commit.edges.1"}}
  }]
}
```

示例仅演示协议，坐标、道路资源和预算须根据当前地图规划。可在 `steps` 中加入第二条独立道路，并使用不同步骤 ID、坐标和对应引用。对象引用路径中的数组从 **1** 开始；道路图的 `from/to` 节点索引仍沿用原接口从 **0** 开始。

`{"$ref":"road1.commit.edges.1"}` 解析为实际提交结果的数值；预览参数只能引用前面的步骤，验收可引用本步。未知路径会报错，不当作零。`expect` 是返回结果内路径到期望标量的映射，必须类型和值都匹配。

## 支持范围与验收

可用预览：`preview_road`、`preview_network`、`preview_road_graph`，以及 `build_warehouse`、`build_heliport`、`build_helipad`、`build_airfield`、`build_water_facility`、`build_headquarters` 的设施起建预览。仍取决于对应原生接口是否返回完整报价及碰撞检查。结构预览、未知报价和碰撞不允许提交。

独立验收查询：`get_entity`、`get_facility_config`、`get_facility_access`、`get_facility_inventory`、`check_road_junction_path`、`check_network_junction_path`。按工程目标填写检查，例如实际接路需要路径检查，仓储工程需要库存或配置检查。仅检查 ID 存在不代表道路通达、库存共用或运营成功。

v2 支持以下运输步骤，同样填写 `id/preview/arguments/max_cost/checks`：

| `preview` | `arguments` | 内置检查 |
|---|---|---|
| `create_line` | `station_groups`（2～8 个）、`name` | 逐站核对默认 station=0/terminal=0 的原生终端及网络实体，创建一次后读回所有权及站序 |
| `preview_line_edit` | `line`、`stops`（沿用原接口显式装载/终端配置） | 新鲜配置预览、单次更新和配置签名读回 |
| `buy_vehicles` | `depot`、`model`（资源名）、`mode`（原生运输模式名）、`count`（1～16） | 基地所有权、模式、出口、载具 carrier、原生零件报价；逐辆采购后读回车型、基地及在库状态 |
| `assign_vehicles` | `line`、`vehicles`（1～16 个 ID 或引用）、`stop_index` | 逐辆检查所有权、在库状态，再单次分配，读回线路、停止标志及 noPath |
| `accept_departure` | `vehicles`、`line`、`seconds`（1～120），或 `fleets:[{line,vehicles}]`、`seconds` | 跨更新帧确认实际离库/运动、目标线路及无原生线路/寻路故障 |

运输步骤除了采购外 `max_cost` 必须为 0。采购预算是**整批上限**，逐辆重新报价；剩余预算和其他工程承诺仍保留。批量购买由接收器逐辆执行原有 `count=1` 命令，每辆单独记录回执和读回，部分失败后不重买已购车辆。当前是单模型默认配置采购；固定多单元编组需原有专用适配，不在此采购入口内。

新线路沿用原有默认装载配置；需要指定货品、装卸、终端时，在购车前加入 `preview_line_edit` 步骤。终端存在和基地有出口不等于全链路通达：规划仍须先验证产业内部终端、外部路网、运输走廊及基地的连续连接。不能以采购试探缺路，也不能将 carrier 一致描述为所有车型细节兼容已通过原生验收。

### 运输工程示例

以下 Python 片段构造 MCP 的 `steps` 参数；基地、站点、车型及预算需替换为当前地图已核实的数据：

```python
def ref(path):
    return {"$ref": path}

line = ref("route.commit.line")
vehicles = [ref(f"fleet.commit.bought.{i}") for i in (1, 2)]
steps = [
    {"id": "route", "preview": "create_line", "max_cost": 0,
     "arguments": {"station_groups": [200, 201], "name": "Supply route"},
     "checks": [{"command": "get_entity", "arguments": {"id": line},
                 "expect": {"id": line}}]},
    {"id": "fleet", "preview": "buy_vehicles", "max_cost": 200000,
     "arguments": {"depot": 300, "model": "vehicle/bus/old_bus.mdl",
                   "mode": "BUS", "count": 2},
     "checks": [{"command": "get_entity", "arguments": {"id": v},
                 "expect": {"id": v}} for v in vehicles]},
    {"id": "assign", "preview": "assign_vehicles", "max_cost": 0,
     "arguments": {"line": line, "vehicles": vehicles, "stop_index": 0},
     "checks": [{"command": "get_vehicle_motion", "arguments": {"vehicle": v},
                 "expect": {"vehicle": v}} for v in vehicles]},
    {"id": "depart", "preview": "accept_departure", "max_cost": 0,
     "arguments": {"line": line, "vehicles": vehicles, "seconds": 45},
     "checks": []},
]
```

`accept_departure` 必须为最后一步，`checks=[]`，采用内置实际投运判据。多线路可以用 `fleets` 在同一步验收（最多 8 条线路组，每组最多 16 辆）；只有全部指定车辆通过才完成工程。

观察开始时若已有真实投运证据，可立即通过；否则接收器以比较并交换方式从暂停切换到 1 倍速。使用实际运动分量或两次位置变化，车辆必须不在基地、不处于回库状态，归属目标线路，未被停止且无原生故障。未知字段不当成功，不要求完整往返、上下客或交货数量。所有车辆通过、超时或原生故障时恢复暂停；用户自行改速时结束观察且不覆盖用户速度。接收器安装代次/玩家/世界变化、游戏时间倒退或速度命令结果未知时冻结，须核对状态。事件队列超过 15 秒未处理同样冻结且不重发。代次不变且时间未倒退的重载不能仅凭这些字段识别，不声称检测所有同存档重载。

`complete=true` 表示全部声明的检查通过；只有计划包含且通过 `accept_departure` 时才代表实际投运验收。城市供货和长期运营目标不由此判为达标。拆除、贷款和仅结构预览的改造仍不包含。

## 预算及边界

- 每工程 1～8 步；每步 1～4 项验收，每项 1～8 个期望字段，终端投运步骤使用内置验收。完整输入最多 8192 字节，实际可容纳步数取决于参数大小。
- 整项预留未建步骤的 `max_cost` 总和，另加 `reserved_cash`；支出后必须严格高于 `cash_floor`（至少 500 万元）。每步提交前刷新现金和暂停状态。
- 优先读取 `balance`，该字段缺失时读取原生 `accountBalance`；两者均不可读则拒绝，零余额不视为无限资金豁免。只有用户明确授权后传入 `allow_no_costs=True`，且每次检查确认原生 `baseConfig.noCosts=true`、玩家原生余额为 nil，才豁免现金保留检查；仍逐辆核对原生报价和步骤预算上限，不启用作弊或贷款。
- 单步原生报价不得超过该步上限。不借款，不自动缩减方案。
- 每次执行前检查剩余接口额度；不足则阻塞，由外部按已有授权安全重置额度后续作。不会在工程内部重置 pending。
- 步间超过 20 秒软时间预算时返回 `yielded`，显式续作；单个原生操作不能据此保证在 20 秒内完成。
- 最多保留 32 项工程，每工程最多 32 次执行/续作信封、256 个子请求。达到上限拒绝新增，不清除去重记录。

## 失败与恢复

| 状态 | 处理 |
|---|---|
| `blocked` | 未提交步骤被预览、预算或参数拒绝；解决原因后续作，已完成步骤不重复 |
| `acceptance_failed` | 已提交成功但额外检查失败；续作只重读该步验收，不重建 |
| `yielded` | 在步骤边界让出，续作从未完成位置开始 |
| `observing` | 接收器跨游戏更新帧观察实际投运，保持工程写锁；可读取，不取消/重发/并行建设 |
| `unknown` | 提交回执丢失、原生 pending 或建造结果无法确认；冻结后续写入，不自动重发 |
| `complete` / `cancelled` | 终态，不能续作；取消保留已建成果 |

工程计划不可在续作时修改。需要调整方案时，先确认结果已知，再取消剩余步骤并为尚未完成的工作创建新工程。跨会话/玩家/世界不自动续作。

外层请求超时也不能重新发送 execute/resume。先按原请求 ID 核对回执，再读取工程和记录的子请求。未知状态及异常中断留下的 `running` 不提供自动解除入口；须诊断实际原生状态，不能删记录或假定失败后重建。

测试入口：`server/tests/test_construction_project.py`、`server/tests/test_project_transport.py`。除施工流程外，覆盖两条线路四辆车统一验收、显式线路配置、部分采购后的报价阻塞与续作、购车回执丢失、分配读回失败、观察超时续作、原生故障、未知通知、用户改速、接收器重载及基地内运动不算出库。模拟测试不替代实机验收。


2026-10-16 旧观察故障的限定恢复：`cancel_project` 可核对旧版错误的原始耐久回执后，仅取消剩余观察。支持已成功切换 1 倍速后的错误实例身份判断，以及 `set_game_speed` 明确返回 `Callbacks are currently disallowed` 的提交前拒绝。后者要求已暂停、原请求恰为唯一 pending、前面所有工程步骤完成、首次变速回执成功，并重新核对玩家、世界、车辆所属线路与故障状态。保留失败回执及核对证据，不重发变速或重建工程；其他超时、回调丢失或未知错误仍不能解除。
