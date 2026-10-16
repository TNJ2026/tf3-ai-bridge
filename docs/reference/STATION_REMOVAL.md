# 公路货站受保护拆除接口

2026-10-15 新增，能力标记 `stationRemovalVersion=1`。离线测试通过；尚未加载新版并进行原生拆除验收。

## 接口

- `preview_station_removal(entity)`：接受独立模块化公路货站的 construction 或 station ID。
- `commit_station_removal(preview_token)`：公开 MCP 工具先保存并验证独立备份，再提交一次。原始 no_gui 命令另需 `backup_save`，主机检查同会话、generation、120秒内的保存凭据以及磁盘签名和 SHA-256。
- `get_station_removal_operation(operation_id)`：使用预览令牌查询、独立读回，绝不重新派发拆除。

仅支持 `::/stations/street/modular_street_station/modular_terminal.con` 的纯货运终端。拒绝客运或混合站、共享站组、线路仍引用、车辆仍使用站内网络、等候人员、非空自有库存、附属车库/产业/城市建筑和未知读取结果。库存检查针对拆除对象自身，不清空或删除其配送覆盖的城市/产业库存。

保持暂停，预览令牌绑定会话、玩家及额度轮次，有效60秒且仅可使用一次。提交时重新读取设施、站组、线路、车辆、相邻道路及节点配置。原生删除提案仅允许目标建筑和其内部网络删除，边界配置只允许清除内部道路引用，其他改动拒绝。不绕过碰撞，不将删除提案传给不支持该路径的 makeProposalData。

预览明确返回 `nativePreview=false`、`validation=structural_and_native_proposal_scope`，不是完整原生可施工预览或报价。接口不提供可靠拆除净费用，不能将未知费用当零；如执行任务有现金/预算约束，需另行满足该约束。

提交意图在原生调用前持久化。拆后核对建筑及所有原站点/子实体消失、外部道路和节点配置保留、既有线路及车辆配置不变且未新增 noPath。未知、异常或部分结果保留 pending，通过原请求/操作结果核对，禁止重发、清锁或自动回滚。纯设施拆除不删除路边接路、售车、改线或恢复监控。

## 安装和使用状态

本轮将候选脚本安装到当前 staging_area 本地模组，旧脚本备份与编译结果存于 `output/station_removal_20261015/deployment.json` 所在目录。安装不会热更新运行实例；需用户重新加载刚保存的游戏，再检查新会话的 `stationRemovalVersion=1`，重新解析目标、预览。公开 MCP 工具列表需要重新连接服务才能刷新。

当前 Wareham 两个旧货站仍保留，未通过本接口执行拆除。首次实机验收应独立备份后单站提交、独立读回，不以离线测试代替原生验收。

测试：`server/tests/test_station_removal.py`；与车库拆除、no_gui 和 UI 通道相关回归共214项通过。覆盖原生 userdata 指纹、未使用站点成功拆除、依赖拒绝、预览后变化、外部道路越界、备份/能力门槛、重复提交、延迟回调、失败及部分结果。

## 首次实机预览与兼容修正

2026-10-15，用户重载后会话 `6715.442:table: 00000081323C6E20` 已确认 stationRemovalVersion=1，仍暂停，现金44,415,656。四条现有线路及新停靠点站序保持。

原请求 `c08791836013407ea8b9813841317dc6` 在预览阶段失败：`$.terminals.1.vehicleEdges.1` 的文档 EdgePos 字段 edgeId/param 均不可读，尚未生成删除提案、未提交拆除。两座旧货站仍在。

候选修正增加严格 EdgeId 兼容读取：仅在两个 EdgePos 字段均缺失、entity/index 都为有效非负整数时保留实际边标识；部分可读或未知结构仍拒绝。此备用结构尚待加载后确认，不宣称已确认运行时具体类型。新增指纹标记 `stationRemovalFingerprintVersion=2`，218项相关测试通过。候选已安装，备份和编译结果位于 `output/station_removal_20261015/fingerprint_v2`，需要再次加载才生效，尚未实机验收。

## 实机拆除验收完成（2026-10-15）

用户明确提交后，在会话 `6923.246:table: 0000008008363970` 对 Wareham 旧货站23747、23560逐座完成独立备份、新鲜预览、单次提交及独立操作读回；两座均 `nativeAccepted=true`、`verified=true`、`issues=[]`。站点及子实体、内部道路消失，相邻道路和节点配置保留，4条线路与7辆载具配置保持，无新增noPath。游戏保持暂停，现金44,415,656；固定完工存档 `wareham_auto_20261015` 已覆盖并验证保存成功。未做拆后长期模拟或重载验证。

证据：`output/station_removal_20261015/live_commit_pair.json`。EdgeId兼容读取已通过本次原生预览与提交；这些样例不证明其他设施类型均可拆除。
