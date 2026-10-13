# 机遇与补贴任务接口

2026-10-13 用户确认：工人运输机遇（deliver_workers）要求人数取目标产业 get_industry_bonuses(industry).workers.requiredVisitors，即产业工人加成触发人数。按该人数规划居民到产业内部客运换乘点的客运路线，配备兼容车辆并开始运营；不再因 get_subventions 或 preview_subvention 未单独返回合同人数／完成判据而阻塞评估、接取或实施，也不另设需补充合同人数接口的前置条件。保留当前UID、可接取状态、期限、完整工程费用、现金底线、承诺资金、道路连续通达和原生接口保护；requiredVisitors 本身不可读时如实记录未知。车辆投运按实际出库、正常执行线路且无原生故障验收；机遇最终完成仍以该UID的原生合同状态确认，不以建线或出库代替履约。此规则为用户确认的执行口径，不冒称新增接口实测；文档更新不恢复监控、不接取机遇或施工。

查询、单次接取与规则轮询始于桥接 0.12.0；0.12.1 修正自定义装载比例估算及接取确认。本文按当前源码整理，接口存在不等于当前存档已完成实机验收。

通知中的机遇对应原生 `Subvention` 状态。通知历史仅有编号，任务详情以原生脚本状态为准；不直接改写任务或账户。接受任务会获得预付款，失败可能扣除包含预付款与额外罚款的金额，接取需在用户授权范围内进行。

## 1. 工具选择

| 工具 | 用途 | 是否接取 |
|---|---|---|
| `get_subventions(assess=True)` | 查询提议、活动、完成与失败任务，估算已有货运服务 | 否 |
| `accept_subvention(uid, expected_...)` | 对一个当前提议发送原生接取事件 | 是，单次 |
| `subvention_autoaccept(action="status")` | 查看运行策略、日志、尝试及 pending | 否 |
| `subvention_autoaccept(action="run_once", dry_run=True)` | 单轮读取、评估并说明接受／拒绝原因 | 默认否；`dry_run=False` 可接取 |
| `subvention_autoaccept(action="start", dry_run=True)` | 立即执行一轮并在 MCP 进程内轮询 | 取决于 dry-run |
| `subvention_autoaccept(action="stop")` | 停止后续后台轮询 | 不取消已经发送或已接受的任务 |

自动轮询只随当前 MCP 服务进程运行，不在 mod 的 `update()` 中执行。服务退出即停止；日志写入桥接目录 `subvention_autoaccept.json`，它不是可自动恢复全部尝试状态的持久化任务队列。

## 2. 明确指令直接接取（2026-10-12）

1. 用户或获授权提示词已经明确要求接取时，无需再次询问。需要定位目标时，用 `get_subventions(assess=false)` 读取当前原生 UID、目标和可接取状态；不用旧通知编号猜测，也不擅自替换任务。
2. 对当前可接取的目标直接调用一次 `accept_subvention`。不把历史机遇对账、供货分析、运力规划或资金分析作为手动接取前置步骤。可传入已知的 `expected_*` 防止定位后条款变化，无需另做调查。
3. 提交后读回原生结果：`Active` 或有 acceptedTime 的后续历史状态才证明已接取；仅有 `submitted` 表示已提交。结果尚未确认时如实报告，不要求用户先对账才能完成正常接取流程。
4. 同一 UID 已发送不重复发送；移除了“其他旧机遇未确认就拒绝新机遇”的限制。运输通道中其他未决写请求仍按原有规则处理，不通过删除 pending 或重载绕过。

可复用提示词：**“用户明确要求接取机遇时，定位当前对应 UID；若原生状态允许接取，立即单次调用 accept_subvention，不做历史机遇对账，不追加供货评估或确认问题。随后读取接取结果；已发送结果未知时不重发。”**

本更改不启用自动轮询，不更改下节无人值守自动接取策略，也不授权建设线路或购车。下文的旧版拒绝结案工具仅用于兼容历史错误记录，不是正常接取步骤。

原生 `Proposed` 表示尚未接受的报价；`Active` 表示已接取；`Complete`、`Failed` 表示原生记录的最终状态。报价剩余时间与接取后的履约期限不同，按当前状态解释 `remainingDays`。

### 发送阶段与拒绝结案（2026-10-11 修复候选）

适配器记录 `prepared`（原生发送前）、`dispatch_started`（已开始调用原生接口，结果可能未知）、`confirmed`（原生确认）和 `rejected_before_dispatch`（发送前拒绝）。后者保留原错误与已消费令牌，结束对应工作流的 pending；不返回接取成功，也不自动重试。任何已进入发送阶段的异常或超时仍须保持 pending。

`get_subventions` 在原生 Active/Complete/Failed 且 acceptedTime 存在时，按 UID、玩家、资源和 spawnTime 核对并持久保存接取证据。任务以后退出原生列表，不撤销已经确认的接取；这份历史证据不证明当前履约进度或完成状态。未经观察的历史接取仍为未知，不能凭任务消失结案。

旧版“previous subvention accept requires reconciliation”发送前拒绝可使用 `reconcile_subvention_rejection(request_id, expected_session)`。加载版本须在 `get_validation_state` 返回 `subventionReconciliationVersion=1`。接口检查原请求错误、对应工作流及令牌、操作身份、没有该 UID 的发送记录，并拒绝原生已接证据或时间回退；只结案该拒绝，不清除其他未确认提交。主机独立读回 pending，保留原始失败，不接受机遇、不重置额度、不重载、不恢复监控。

离线测试不代表当前运行实例已加载或完成实机验收。部署后须确认版本；需要加载存档时先保存并验证当前进度，不通过读旧档丢弃 pending 来替代正式结案。记录见 `output/subvention_repair_20261011/RESULT.md`。

## 3. 自动接取策略

以下参数用于 `start` 和 `run_once`。后台运行中不能另发手动 `run_once`，应先停止轮询。

| 参数 | 默认值 | 含义与约束 |
|---|---|---|
| `kinds` | `deliver_cargo`、`deliver_cargo_town` | 当前默认货运类型；其他类型不能仅加入列表就获得评估支持 |
| `min_margin` | `1.5` | 估计年运量／任务所需年运量的最低比值，须大于 0 |
| `max_failure_money` | `15000000` | 允许的失败扣款上限，非负；不是推荐风险预算 |
| `min_remaining_days` | `0` | 报价剩余游戏日下限，非负 |
| `max_active` | `5` | 活动任务上限，当前接口允许 1～5 |
| `interval_seconds` | `30` | 后台轮询的真实秒数，`start` 要求至少 5 秒 |
| `dry_run` | `True` | 只记录决策；改为 False 前须已有自动接取授权 |

先以 dry-run 核对拒绝理由、目标服务及估算依据，再在授权范围内启动真实接取。每轮至多尝试一个任务，后续轮次重新读取原生状态。已有 pending 时不再选择新任务。

## 4. 返回结果不能混用

| 自动轮询字段 | 含义 | 后续处理 |
|---|---|---|
| `decisions` | 该轮候选接受／拒绝决定及原因 | dry-run 的 accept 决定没有发送事件 |
| `submitted` | 已发送且当前没有明确发送失败迹象 | 仍等原生状态确认 |
| `pending` | 曾尝试，但尚无原生确认 | 阻止后续接取，继续只读核对 |
| `failed` | 发送失败、异常或回调拒绝 | 仍可能 pending，不能认定世界无变化 |
| `accepted` | 本轮首次确认该尝试已进入 Active／Complete／Failed | 表示接取曾生效，不等于履约成功 |

这些列表不互斥：一次发送可同时位于 submitted 和 pending；一次异常可同时位于 failed 和 pending。`status` 的 pending 表示服务仍保存的未确认尝试。重启丢失内存记录后，必须核对原生任务，不能把空列表当作无任务证明。

## 5. 估算与协调边界

评估查找在生产端装载目标货物、在目标卸货的玩家线路，结合车辆容量、估计周转、装卸及货源年产量。自定义装载按目标货物 `maxLoad` 比例折算；零、缺失或无效比例不计入可用能力。它仍不保证车辆对具体货类的真实适配、实际拥堵与等待，也不能替代完整送货周期观察。

多货物任务、转运网络和共享来源应另行核对，不把单条货物估算推广成整个任务的充分证明。工人和旅客任务没有当前自动货运评估支持。报价窗口与游戏速度有关，历史上观察到的月数不作为固定规则。

当前没有跨任务与城市方案的统一运力、仓储、预算预留；多个任务可能竞争同一来源或车辆。执行者应合并现有承诺并按[操作协调](../guides/OPERATION_COORDINATION.md)安排施工与接取，不能仅因每项任务单独 margin 足够就认为合计可完成。

实现参考：[工具签名](../../server/src/tf3_mcp/server.py)、[轮询与策略](../../server/src/tf3_mcp/subventions.py)。
