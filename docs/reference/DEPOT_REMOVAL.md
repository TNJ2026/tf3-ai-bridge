# 公路车库受限拆除接口

2026-10-11：补齐 headless 的公路车库拆除流程，能力标记为 `depotRemovalVersion=1`。目前通过离线模拟测试，尚未完成原生游戏拆除验收。旧 `bulldoze` 仍不在 headless 白名单内，不自动回退到旧文件通道。

同日实机预览修正：原生公路车库的 `subconstructions` 包含自身 VEHICLE_DEPOT 子实体，不能按列表非空拒绝；仅允许与已校验 `depots[1]` 相同的子实体，其他附属对象仍拒绝。引擎状态增加 `depotRemovalFingerprintVersion=2`；49 项专项测试通过。已安装修正，但当前运行实例实测未热更新，仍须重新加载；第一条预览失败在原生提案和施工之前，pending 为空，两座目标均未拆除。

后续 v3 修正：节点序列化的 `Network.BaseNode` 类型提示不存在，真实 userdata 被判为不透明数据；改用已注册的 `Engine.Component.BaseNode`，预览和读回同时修复。新增原生 userdata 代理测试，确认旧提示复现拒绝、新提示保留位置并检测变化，另验证车辆部件 userdata。52 项专项、292 项相关回归通过。引擎标记 `depotRemovalFingerprintVersion=3`，尚待加载后的实机验证；仍未发送拆除。

后续 v4 修正：安装目录 `api/tealdef/api/engine/util.d.tl` 明确 `createProposalRemove` 返回完整 `Proposal`，不是 `SimpleProposal`。据 `api/type.d.tl` 改用 `toRemove/toAdd/old2new/proposal`、`removedSegments/removedNodes` 等字段；保留完整原生提案提交，不转换简化提案，不跳过范围校验。未知字段直接拒绝，拒绝范围的错误附带 `nativeScope`，成功预览也返回同一范围摘要。测试桩改用完整原生格式并测试 userdata 和十二种越界编辑；65 项专项、305 项相关回归通过。引擎标记 `depotRemovalFingerprintVersion=4`。仍待加载和原生验收。

## 范围和步骤

v5 原生拆除验收（2026-10-11）：用户载入独立测试存档后，在新会话 `43349.63:table: 0000008880025AF0` 确认第五版；盘锦两座空公路车库分别完成独立备份、单次原生提交及独立读回，均为 `nativeAccepted=true`、`verified=true`、`issues=[]`。相邻道路、剩余入口配置及现有车辆保留。证据：`output/panjin_depot_relocation_20261011/removal_pair_v5.json`。后续新建已发生实体编号复用，不能再以旧拆除 ID 是否存在判断旧车库恢复；必须结合类型、位置、会话和操作记录。该验收不证明任意车库或长期模拟安全。

v4 加载后的实机预览识别到合法的入口节点配置替换：西北车库内部边 43297 被删除时，边界节点 42117 必须清除引用该边的转向和横道。旧规则把所有配置替换都拒绝，未提交任何拆除。v5 将相邻节点配置加入预览签名和拆后读回，只接受边界节点成对替换，内容必须精确等于原配置删除车库内部边引用后的结果；其余转向、横道、信号偏好和标志须保留。有信号相位索引需要重映射的情况仍拒绝，不猜测。原生 Proposal 保持原样，无碰撞忽略。85 项专项、325 项相关回归通过，v5 已安装；尚待用户加载及原生提交验收。证据见 `output/panjin_depot_relocation_20261011/V5_BOUNDARY_CONFIG_FIX.md`。

仅支持自有、空置、独立的 `::/depots/road/road_depot/road_depot.con`。不支持铁路车库、车站、仓库或普通道路拆除，不卖车、不移车。必须有用户拆除授权；这项能力不会恢复监控或执行历史拆迁计划。

1. 读取新鲜会话、地图身份、pending、速度及目标。暂停游戏；重载后重新解析实体，不复用历史编号。
2. `preview_depot_removal(entity)` 接受车库或其 construction ID，核对所有权、附属设施、库内车辆、返库车辆、道路及车辆配置，生成一次性 60 秒令牌。
3. MCP 工具 `commit_depot_removal(preview_token)` 先保存独立的 `tf3_depot_before_<uuid>` 存档，确认新文件稳定及 SHA-256 后，才提交拆除。原始 headless 命令还需要 `backup_save`，主机要求同会话、同 generation、120 秒内的已验证保存记录，且磁盘签名和摘要未变；仅提供文件名不能通过。
4. 引擎再次核对暂停、会话、额度轮次、令牌、目标和依赖签名，持久化操作意图后仅调用一次原生 `createProposalRemove` / `applyProposal`，不启用碰撞忽略。
5. 读取 `get_depot_removal_operation(operation_id)`，其中 operation ID 就是预览令牌。核对车库及内部节点/边消失、相邻外部道路/节点保留、已有车辆和线路配置保留且未新增 `noPath`。维护覆盖、未来返库和实际运行需要另行验收。

预览返回 `nativePreview=false`、`validation=structural_and_native_proposal_scope`：它检查原生删除提案的作用范围，不声称通过完整原生可施工验证。删除提案不能送入已知不支持该路径的 `makeProposalData`。若提案包含外部道路、共享内部节点、额外建筑或其他网络编辑则拒绝，不放宽规则强行拆除。车辆清单超过 2048 辆时拒绝；无法读取库内清单、依赖或车辆状态也拒绝。

运行中的车辆可以保留历史 depot 引用，但必须有有效线路且处于 `EN_ROUTE` / `AT_TERMINAL`；库内、返库、无有效线路或未知状态均阻断。此规则不保证拆库后维护覆盖充足，仍须按迁建计划补足新车库并验证进出库。

## 超时与恢复

提交前消耗令牌；错误、超时、部分成功均不重发。引擎保留 `depotRemovalOperations` 和 pending，结果查询仅检查现场。延迟完成且全部不变量满足时可确认并解除该操作的 pending。明确回调失败也不自动清锁或重试，需要查明现场状态。

如果主机仍有未收到结果的请求，先用原 request ID 读取传输回执，不能绕过主机锁新发请求；传输层解锁后再查询操作。换会话/换玩家后自动核对拒绝，历史意图仍保留。额度重置使旧预览失效，不删除已提交操作证据。原生断言不能由 Lua `pcall` 防护。

备份耗时超过令牌有效期时提交会被拒绝；只有确认未发送且 pending 为空后才能重新调查、重新预览，不能自动重试原提交。

## 加载和验证

安装 Lua 脚本不会热更新运行实例。保持暂停，先保存当前进度，再加载已保存的存档；重新连接 TF3 MCP 以加载新的 Python 工具定义。新会话读取 `headless_status` 和 `get_validation_state` 的能力标记，再重新绑定地图与实体。不得自动重载、恢复速度或恢复监控。

首次原生验收在独立保存的测试副本上进行，单个空车库单次提交。静态读回、短时模拟、维护/返库检查和保存重载分别记录，不能把离线通过或目标消失等同于长期模拟安全。

离线入口：`server/tests/test_depot_removal.py`。覆盖正常拆除、所有权、库存未知、返库/未知状态、提案越界、依赖改变、会话/过期/额度失效、重复令牌、延迟/异常/部分成功持久恢复、旧接收器拒绝、备份真实性及 MCP 单次提交顺序。
