# 车辆分配拒绝对账

2026-10-13：新增 `reconcile_assignment_rejection(request_id, vehicle, line)`，通过 HeadlessClient 的命名请求入口使用。需要接收器与原生能力 `assignmentReconciliationVersion=1`。已通过169项相关离线测试，并在用户重载后完成临汾原拒绝请求的单次原生对账与独立pending为空读回。该验收仅证明本次明确拒绝场景；不证明分配故障已修复。详见 [实机记录](../../output/assignment_pending_repair_20261013/RESULT.md)。

仅允许原生持久账本的 pending 精确匹配、原请求为 assign_vehicles/error/ok=false、assigned 为空、唯一失败内容精确为对应车辆 rejected。必须暂停、车辆与线路属于当前玩家、车辆 line=-1 且在库，并由车库清单和线路车辆清单交叉核实。超时、部分成功、异常字符串、冲突状态和其他请求均保留 pending。

成功仅将原请求记为 reconciled_rejected/nativeAccepted=false/retryAllowed=false，保留原始 result，解除该请求的 pending。不会发原生车辆指令、重复分配或宣称线路修复、车辆投运完成。旧请求 ID 仍不可重放。

执行前持有公共工作流锁，核对当前会话/地图/玩家、主机无 pending，归档原回执并核对其车辆/线路与此请求一致。接收器未加载时主机在发布请求前拒绝。提交仅一次，随后独立读取 get_validation_state 与车辆/线路状态。新会话先重新核对地图和旧账本，不假定旧 pending 已消失等于成功。

本次安装不重载、不回档、不清锁、不重置额度，也不恢复监控。当前接口 save/load 受 pending 保护，需要用户手动另存当前现场并载入该新存档，不能载入施工前旧档。之后先验证新能力、地图、车辆和原拒绝账本，再进行单笔对账；若账本缺失或冲突，保留证据停止，不凭主机记录强行写入。
