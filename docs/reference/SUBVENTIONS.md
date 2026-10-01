# 机遇与补贴任务接口

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

## 2. 手动接取顺序

1. 查询当前任务，核对 `uid`、`status`、类型、目标、货物、数量、报价期限、预付款与失败扣款；不用旧通知编号猜测当前任务。
2. 读取已有服务、车辆、实际供给和共享承诺。估算通过不构成完成保证；接任务本身不建路线、不买车。
3. 在授权内调用一次 `accept_subvention`。建议传入当前读回的 `expected_to_deliver`、`expected_target`、`expected_upfront_money` 和 `expected_failure_money`，防止条件变化后仍接取。
4. 保存回执，通过 `get_subventions` 等待原生 `Active` 或后续历史状态确认。事件由原生脚本更新处理，`submitted` 不是接取成功。
5. 超时、异常或任务消失时先核对；不能重发，也不能通过重载清除保护后再试。

原生 `Proposed` 表示尚未接受的报价；`Active` 表示已接取；`Complete`、`Failed` 表示原生记录的最终状态。报价剩余时间与接取后的履约期限不同，按当前状态解释 `remainingDays`。

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
