# mod.io 下载版连接（2026-10-15）

当前通信方式、三种接收器模式及旧 `request.lua` 的条件见[通信通道说明](TRANSPORT_CHANNELS.md)。旧 `file` 通道已在 2026-10-16 只读实测失败后移除。

实机发现：下载版能加载已有脚本，但进程启动后新增的 Lua 请求资源不可见。新鲜心跳不代表请求通道连通。

## 正式修复

发布准备、清理、校验及上传前先阅读[模组发布流程](../guides/PUBLISHING.md)。默认从游戏 Mod Hub → My Mods 上传，不生成 ZIP；`scripts/build_mod_package.py` 仅在用户明确要求 ZIP 时使用，历史产物不代表当前已发布。正式发布副本须启用 userdata 接收器，并排除 `content/tf3_mcp_bridge/no_gui/` 运行时请求及测试文件。外部 MCP 服务及本机路径仍需另行配置；下述安装器用于旧下载版修复和本地诊断。

安装器 `scripts/install_no_gui_diagnostic.py --mode auto` 对 mod.io 路径选择 `userdata`，本地开发目录选择 `demand`。也可显式指定 `--mode userdata`。下载目录拒绝已知不可用的 demand 模式。旧 indexed 仅保留显式兼容用途，约34分钟且空闲消耗槽位，不作为长期方案。

MCP 保持 `TF3_MCP_TRANSPORT=no_gui`。`TF3_MCP_NO_GUI_MOD` 是环境变量名，其值应为本机实际安装目录，并非固定路径。安装器备份、编译检查和原子替换脚本，不自动重载。mod.io 更新可能覆盖本地修改，更新后需重新核对。

使用已有原生目录 `mod_presets`，无需自定义游戏 userdata 目录。每代使用唯一 `tnj_mcp_<generation>_request.preset.lua` 信箱；原生 getAllUserdata/loadUserdata 读取并删除已消费请求，结果沿用现有日志回执。外部 tf3_mcp 账本目录仍保留，不作为游戏 userdata 目录。

空闲不消耗序号，没有旧版34分钟寿命限制。仍校验会话、序号、有效期、请求ID及持久化pending；主机重启只续查原回执，不重发未知操作。外来信箱拒绝覆盖。信箱出现在原生预设枚举中，不宣称对预设界面隐藏。

## 验证与部署

- 原生 A→B 重复读写通过：output/userdata_roundtrip_20261015/RESULT.md。
- 原生双向实验100次正常请求、1次重复及3次非法请求符合预期；空闲无重复，文件清理通过：output/userdata_duplex_20261015。
- 正式接收器离线覆盖301次读取、模拟两小时空闲、重放拒绝、主机重启恢复、外来信箱保护及发布失败保留pending。
- 全套2162项及4个subtests通过；另1项HTTP测试因进程代理返回502，移除该进程代理后单独通过。
- 正式接收器已部署，代次 `2e8c6c030c6c421a8041f128968456b6`，见 output/modio_userdata_receiver_20261015/deployment.json。**真实 MCP 请求、原生保存重载及外部服务重启后读取均已通过**。完整证据见 output/modio_userdata_receiver_20261015/RESULT.md；不据此宣称无限期内存稳定。

## 首次加载

磁盘更新不会替换内存Lua。此前内存运行已结束的独立测试，MCP曾返回 `NoGui heartbeat stale; no dispatch`，无法自举重载。用户手动加载新版后，已实际通过MCP保存并重载成功，后续可使用 [原生MCP读档](LOAD_GAME.md)。不使用过期心跳发送请求，不清pending绕过恢复。

旧未知只读请求和不可重放标记保留。新会话需绑定受限恢复流程，独立核对状态、地图与原生pending后解除切换门槛。不恢复暂停监控。
