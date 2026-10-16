# 通信方式与接收器模式

更新：2026-10-16。以下名称均为本项目配置，不是 TF3 官方参数或 MCP 标准参数。

本次全项目命名统一版本为 0.12.31：配置值、`TF3_MCP_NO_GUI_MOD`、`no_gui_status` / `bind_no_gui_session` / `send_no_gui_request` / `read_no_gui_result`、Python 模块与类、Lua 常量、日志标记、请求目录及账本均使用新名称；不再保留旧命名别名。重新连接 MCP 服务后加载启用了新版模组的地图。当前安装完成，2352 项测试及 4 个子测试通过。用户进入地图后，新 MCP 进程的连接、ping 往返及 5 项只读批处理均实测通过：游戏状态、地图、城市、线路、载具在 1 个批次完成，逐项成功，无 pending。当前实测为 demand 模式，不扩展为 userdata/indexed 的本版实测结论。见[现场证据](../../output/no_gui_rename_20261016/live_verified.json)。历史证据文件及其引用路径保留原样。

## MCP 服务通信方式

当前只支持 `TF3_MCP_TRANSPORT=no_gui`，也是未配置时的默认值。`file` 已移除，显式配置该值会报错，不静默切换。

删除后的 0.12.30 接收器已部署并重载，no_gui 地图、线路、载具读回及 CLI 连接通过。实测和移除记录见 [验证记录](../../output/file_transport_retest_20261016/RESULT.md)。现有 MCP 服务进程仍须重启才能加载 Python 侧变更。

`no_gui` 表示无需手动操作桥接面板。游戏仍须启动、加载地图并启用模组；内部仍使用游戏 GUI 上下文及引擎事件。它不表示无窗口运行、无 GUI 回调或不使用文件。

## no_gui 接收器的三种模式

| 安装器 `--mode` | 请求载体 | 适用情况 |
|---|---|---|
| `demand` | 按会话和序号创建一次性 Lua 资源请求文件 | 本地开发模组；2026-10-16 工程批处理实测使用此模式 |
| `userdata` | 已有原生目录 `mod_presets` 下按接收器代次命名的可复用邮箱 | mod.io 下载版默认选择，详见[下载版连接](MODIO_CONNECTION.md) |
| `indexed` | 预建 1024 个编号 Lua 资源槽位 | 有限诊断/兼容模式；空槽轮询也会推进，耗尽后停止 |

`auto` 是安装器选择规则，不是第四种模式：mod.io 安装目录选择 `userdata`，其他目录选择 `demand`。实时心跳对 indexed 模式使用 `bounded` 标签。

`demand` 和 `indexed` 的请求资源位于安装模组的 `content/tf3_mcp_bridge/no_gui/`。`userdata` 使用原生邮箱，不依赖该资源目录发现新请求。三者结果均沿用日志回执。

## 旧 file 通道已移除

2026-10-16 在已加载地图、no_gui 心跳正常且没有未决请求的条件下，向旧固定 `request.lua` 发送一次只读 `get_game_state`。6 秒内没有匹配响应，测试前后均没有 `heartbeat.lua`；同一会话的 no_gui 前后读取正常，游戏时间和暂停状态未变。证据见 `output/file_transport_retest_20261016/result.json`。结论限定为当前环境，不推断所有历史游戏版本。

按用户“不可用就删除”的要求，桥接源码 0.12.30 移除了旧消息文件读写、轮询及旧外部事件订阅；MCP 服务移除 file 配置入口及回退分支。固定 `request.lua` / `response.lua` / `heartbeat.lua` 不再是生产接口。

共享路径解析和十六进制消息编码仍由 no_gui 的 userdata 模式使用，因此保留。历史 Python `Bridge.call` / `heartbeat` 只保留明确的移除错误，避免旧脚本悄悄执行；CLI 已迁移到 no_gui。历史命令测试需要的旧协议模拟器仅保存在 tests 夹具中，不随生产接收器安装或运行，也不作为旧通道可用的证据。

no_gui 的三种接收器模式不受此次移除影响。未知结果仍须核对原请求，不能重发或改用其他入口绕过保护。

## 配置与重启

推荐 `TF3_MCP_TRANSPORT=no_gui`，`TF3_MCP_NO_GUI_MOD` 指向实际安装的 `content/tf3_mcp_bridge`。环境变量、工具名、模块名及请求目录已统一为 no_gui；部署时须迁移现有账本，不能丢弃未决请求或去重记录。

仅修改 MCP 配置或 Python 服务代码时，重启 MCP 服务即可；安装或更换游戏接收器代码/模式后需要重新加载游戏地图。不要把这两种重启混为一谈。

代码依据：[`server.py`](../../server/src/tf3_mcp/server.py)、[`bridge.py`](../../server/src/tf3_mcp/bridge.py)、[接收器安装器](../../scripts/install_no_gui_diagnostic.py)、[`bridge.script.lua`](../../mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua)。
