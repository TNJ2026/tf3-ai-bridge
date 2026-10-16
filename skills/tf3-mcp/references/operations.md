# 日常查询、规划与执行

文档路径相对当前项目，按任务读取，不默认加载全部历史记录。

## 调查与规划

- 读 `docs/reference/READ_BATCH.md`。已知参数且独立的白名单查询用 `read_planning_data`，客户端每批最多 8 项/8192 字节。先取真实 ID，再下一轮详情；整批不是原子快照。保留已有聚合快照，不为凑批扩展调查。
- 逐项检查 executed/ok 和子结果 available/complete，未知不当零。仅明确时间/大小限制按文档单项补读一次；原生错误、通信超时和会话错配不自动重发。
- 普通路线读 `docs/guides/ROUTE_PLANNING.md`，复杂组合再读 `PLANNING_WORKFLOW.md`、`GROUPED_CONSTRUCTION_WORKFLOW.md`。确认真实需求、生产配方、原料/中间品、库存和可复用设施，找到首个合理可运营方案后停止无关调查。
- 核实产业内部终端→外部接口→运输走廊，以及基地出口→走廊的完整通达；靠路、自带道路不证明已接入。水运、铁路、航空分别核对载具、终端、路径和维护。
- 按当前项目规则，城市卸货使用支持目标货品的独立道路停靠点，与公交分离，尽量在实际需求区边缘且覆盖有效。生产源及中转按各自功能规划；不自动拆改既有设施。
- 共库按真实库存 ID，库存去重；仓库不会自动配送。增运比较兼容载量、车次、原生噪音/污染、维护和完整费用，不按名字猜性能。
- 只规划交付路线、设施、费用、未知和验收点。全部规划完成后按项目规则至多调用一次 `export_planning_report`，不在选址中反复展示、不自动开 HTML；用户当前展示偏好优先。

## 授权施工

先读 `docs/guides/OPERATION_COORDINATION.md` 和相关接口文档。

1. 核对授权、预算、现金底线、未完工程承诺、活动合同及共享运力。其他任务的融资、豁免或无限资金许可不继承，不预支完成奖励。
2. 按公共工作流锁串行协调调查→备份→预览→单次提交→独立读回；单请求锁不保护整条工作流。人工、自动接取或其他工程冲突先协调，不争锁或删锁文件。
3. 核实新备份，刷新资金与实体，以当前原生预览、报价、碰撞和兼容检查决定提交。结构预览不冒充完整预览，未知碰撞/报价不强行提交。
4. 依赖步骤使用独立读回的真实结果；道路替换、人工改动后刷新引用。不用 ignoreErrors 或任意 eval 绕过保护。
5. 验证完整路径后购车，显式配置装卸与终端；不通过反复购车/分配试探缺路。

### 工程批处理

多步施工先读 `docs/reference/CONSTRUCTION_PROJECT.md`，确认实时 `projectBatchVersion=2` 和具体支持范围，可使用 `execute_project` 逐项预览、建造、验证。

- 工程非原子事务，不回滚已完成内容。持久化 project_id；`get_project` 查进度，observing 只读等待，yielded/blocked/acceptance_failed 按精确续作点处理，unknown 冻结写入。
- 按文档使用前序步骤真实引用和索引；验收检查接路/库存/配置，不仅实体存在。部分采购失败不重买成功车辆。
- 当前入口 cash_floor 至少 500 万元，另保留 reserved_cash，服从当前更严格的任务/接口条件。skill 不取消工具保护。
- `accept_departure` 可能自动从暂停切 1 倍速再恢复；用户禁止改速时不加入该步骤，改为只读观察并记录待运行验收。其他脚本也先核对副作用。
- 额度不足按 `docs/reference/OPERATION_QUOTA.md`，当前授权覆盖时使用新鲜 CAS 参数重置、独立读回并重新预览；不增预算、不解除 pending。

## 装卸与验收

读 `docs/reference/CARGO_LOADING.md` 和 `docs/guides/CARRIER_ACCEPTANCE.md`。

- loads 是逐站装载/保留列表：源头 `[真实货品ID]`，仅卸货目的地显式 `[]`，途经站按需保留；不可全站复制同一列表。省略字段可能保留旧配置。
- force_unload=false 允许正常卸货，不用强制卸货绕过错误/满库存。接口货品 ID 不加 1，原生 Lua 数组读回才考虑偏移。
- 独立读回 LINE 的站序、终端、装卸并检查原生告警。noPath=false 不替代装卸检查；未知 lineIssues 保留原参数定向诊断。
- 常规投运需实际离开基地、正常执行指定线路且无原生线路/寻路故障；配置成功不等于投运。不额外等待完整往返、回库或交付数量。
- 用户要求货物送达时，另取实际交付证据；城市供货率、客流和合同完成另行验收。任务消失不等于完成，工程 complete 只代表其声明检查通过。

## 机遇、监控与恢复

- 机遇使用 `get_subventions(assess=false)` 定位当前 UID，按 `docs/reference/SUBVENTIONS.md` 和当前授权核对期限、完整链路、报价及承诺资金。工人机遇人数按项目规则读目标产业 `get_industry_bonuses.workers.requiredVisitors`，最终只认该 UID 原生终态。
- 用户要求监控时读 `docs/guides/MAIN_CITY_DEVELOPMENT_MONITOR_PROMPT.md` 及本任务策略/检查点，用平台调度工具。间隔、目标数、资金和通知取当前任务，不套其他城市政策，停止后不自动恢复。
- 故障先查现场、原请求和相关实体；冻结未知写入。明确安全的参数纠正、配置修复或受支持替代方案验证成功后继续，不重复同一失败尝试。当前策略若限制每事件三方案，跨轮累计。
- 部分成功保留成果；改变工程计划前确认请求已终结，只对未完成工作建新方案。无安全恢复路径时停相关执行，按当前监控约定暂停并报告阻碍与恢复条件。

## 专项文档

| 场景 | 项目路径 |
|---|---|
| 自动贴路 | docs/reference/AUTO_ROADSIDE_PLACEMENT.md |
| 城市面板 | docs/reference/TOWN_OVERVIEW.md |
| 产业加成 | docs/reference/INDUSTRY_BONUSES.md |
| 通知 | docs/reference/NOTIFICATIONS.md |
| 保存/读档 | docs/reference/NO_GUI_SAVE.md、docs/reference/LOAD_GAME.md |
| 恢复控制器 | docs/guides/AUTONOMOUS_RECOVERY.md |
| 模组更新清理发布 | 另读 docs/guides/PUBLISHING.md，不自动发布上传 |
