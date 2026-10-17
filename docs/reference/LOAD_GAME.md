# 无界面原生读档

2026-10-13：已在当前测试地图完成原生读档、新会话及保存前后地图身份比对，并用于加载贴路修复版本。全程未使用computer-use；游戏保持暂停，pending已结束。见 [原生读档实测](../../output/native_load_20261013/RESULT.md)。这是有界读档验收，不等同于崩溃自动恢复。其他环境首次安装仍需载入新版桥接。

## 使用入口

- MCP `load_game(slot, expected_session)`：明确指定存档，先独立备份当前暂停进度，再发送一次读档请求，等待新会话并读取游戏状态、地图和原生 pending。
- MCP `verify_loaded_game(request_id)`：中断或超时后，只续查原来的读档请求，绝不重新读档。
- Python `NoGuiClient.load_game(...)` 与 `verify_loaded_game(...)` 同上。
- CLI `scripts/load_game.py` 提供 `load --slot <槽名> --session <当前会话>` 与 `verify --request-id <原请求ID>`；前置参数为 `--bridge-dir <桥接目录> --mod-content <模组内容目录>`。设置 `PYTHONPATH=server/src;scripts` 后使用项目 Python 执行。

启用能力通过 `no_gui_status.receiver.loadGameVersion=1`、`loadGameAvailable=true` 确认。首次安装仍需手动载入一次新版脚本；磁盘代码更新不改变当前运行的 Lua 状态，也不通过旧通道注入代码。MCP 服务需重新加载 Python 代码才能显示新命名工具；CLI 可直接使用新代码。

## 支持范围与证据

首版仅接受本通道曾保存并完成文件校验的本地 `.sav` 槽，保留原始存档和回执。槽名限定 1～80 个 ASCII 字母、数字、下划线和连字符，不接受路径、后缀、Windows 设备名、云端或内置地图。人工保存、未校验存档和任意路径尚未接入。

读档前重新比对目标文件签名和 SHA-256，并创建新的 `tf3_before_load_<uuid>` 备份；失败时不覆盖或删除目标。要求游戏暂停、会话匹配、公共工作流锁、主机和引擎无 pending。低层 `send_no_gui_request(kind="load", command="load_game", arguments={slot, backup_save}, expected_session=...)` 也必须具备10秒内的原生状态/pending读数和120秒内同会话、同游戏时间的已校验备份。

原生端遵循游戏自带 `gui/menu/savegame_react_util.tl`：从 `app.findAllSavegames(app.SaveGameNamespace.getSavegame())` 找到唯一同名存档，使用其真实 `path`、`saveName` 构造 `api.type.SavegameId`，调用 `app.setWaitForStartReadyGame()` 和 `app.loadGame(saveId,false,nil)`。不操控窗口、键鼠，不重启游戏，不修改存档或自动改速。

回执分阶段：

1. `requested=true, verified=false` 只表示准备发起原生调用。
2. 同一加载代次的新会话出现，文件仍未变化，才标记 `reloadObserved=true`。此时仍禁止写入，只允许只读调查及 `get_validation_state`。
3. 新会话独立读回游戏时间、暂停状态、原生 pending、地图，以及保存回执中可用的玩家/世界身份后，才返回 `verified=true`，清除读档校验门槛。`checkpointFieldsVerified` 明确实际比对的字段。

旧保存回执可能只有游戏时间；地图概要在新会话重新读取并生成身份摘要，不能声称与旧存档中未记录的地图摘要做过比对，因此结果含 `savedMapIdentityAvailable=false`。旧实体引用、预览与规划缓存全部失效，后续施工重新调查。该验收不证明线路实际运行或长期模拟安全。

## 中断与失败

2026-10-17 人工恢复运行的显式核对：用户确认在本次原生重载后手动恢复运行时，可调用 Python `no_gui_load.reconcile_manual_resume(host, request_id, expected_session, user_confirmed_resume=True)`，仅核对原请求，不重新读档。要求已收到成功原生回执并观察到准确的新会话、无主机及原生 pending、10秒内的状态/地图/验证读取、玩家与世界一致、读档前后地图摘要相同、目标及独立备份文件哈希未变、游戏时间严格前进、接收器代次符合原记录或已核验部署。缺少任一证据则继续阻止写入。调用前持有公共工作流锁；该函数自身取得账本锁。

此路径仅适用于用户明确确认的手动恢复运行，不用于未知自动恢复、错档、失败回执或一般超时。保留原 `loadExpected`；结果标记 `checkpointTimeMatched=false`、仅玩家/世界字段通过精确检查，并记录人工确认和时间前进证据。默认 `verify_load` 仍要求暂停且时间完全匹配，不自动调用此恢复入口。当前 Citaro 现场用户确认后已完成此核对，保留期间进度，再暂停修改、读回并恢复1倍速；46项读档测试通过。

2026-10-13 桥接升级续验：重载加载新安装代次时，普通校验仍会拒绝与原代次不同的接收器。若这是本次计划中的升级，可对原请求使用 `verify --request-id <原ID> --deployment-evidence <安装器deployment.json>`（Python `verify_loaded_game(..., deployment_evidence=...)`）。必须核对安装记录和脚本均早于原读档请求、安装路径与SHA-256未变、脚本代次与实时接收器一致，以及目标/独立备份文件未变。仅补记预期升级证据，随后仍检查原生读档回执、新会话、时间、身份和pending；不清pending、不重发load、不修改原请求generation。没有匹配安装证据时保留阻塞，不能泛化为接受任意新会话。

读档意图先持久化，再发布一次性请求。超时、日志轮转、原生错误、错误会话/存档或状态不符均保留未决记录，不重发、不清 pending、不重置额度。超时后只用原请求 ID 续查；读档成功但读回中断时，`loadVerification` 持久保留并阻止新写入。原生函数报错后的回执不能被后来一次人工重载当作成功。

该接口仅用于用户明确要求的读档，不由监控、施工失败或文档更新自动调用；不恢复暂停的监控，也不纳入崩溃恢复控制器的自动启动路径。
