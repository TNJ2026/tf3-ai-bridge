# Agent 首次连接完整指南

适用：首次使用 TF3 AI Bridge、重新配置 MCP、切换本地版与 mod.io 下载版，或核查连接失败。本文只完成安装配置与只读验证，不自动施工、借款、改速、读档或恢复监控。

## 1. 理解需要的两个组件

- **游戏模组**：在游戏中启用并随地图加载，执行游戏原生查询和操作。
- **本地 MCP 服务**：本项目 `server/` 中的 Python 程序，由支持 MCP 标准输入输出的 Agent 客户端启动。

模组不包含 AI 模型，也不会自动安装或配置客户端服务。当前通信方式是 `no_gui`，表示无需操作桥接面板；游戏仍须启动并进入地图。旧 `headless` 命名与 `file` 通道不作为当前配置入口。

开始前读取根目录 [AGENTS.md](../../AGENTS.md)。历史城市编号、接收器代次和已通过的测试记录不能作为当前地图事实。

## 2. 准备模组、源码与依赖

1. 从 [mod.io 模组页面](https://mod.io/g/transportfever3/m/transport-fever-3-ai-bridge-3-ai) 下载模组，在创建或载入地图时启用。
2. 从 [GitHub Releases](https://github.com/TNJ2026/tf3-ai-bridge/releases) 下载对应版本的源码并解压。项目根目录应包含 `README.md`、`server/`、`mod/`、`docs/`。
3. 检查 Python 和 uv，版本要求以 [pyproject.toml](../../server/pyproject.toml) 为准（当前 Python 3.11+）。复用已安装且正常的依赖，不盲目升级其他项目环境。
4. 在项目的 `server/` 目录安装运行依赖：

```powershell
uv sync
```

普通连接无需 `--extra test`。若 Python/uv 未安装，按用户环境完成必要依赖安装；下载或执行安装程序前核实来源。Windows/Steam 是当前安装流程的验证环境，其他系统的路径与流程需现场确认。

## 3. 自动找到实际加载的模组

用户通常无需手工提供下载目录。Agent 按下面顺序发现候选并验证，避免全盘扫描。

### 3.1 先查已有配置

读取客户端中 `tf3` 服务的 `TF3_MCP_NO_GUI_MOD`，如项目本地 `.mcp.json`、`.codex/config.toml` 或客户端实际使用的配置。只读取必要字段，不打印其他服务凭据。检查路径及 `bridge.script.lua` 是否存在；旧配置存在不代表仍有效。

### 3.2 查 mod.io 下载根目录

Windows 常见入口是 `%PUBLIC%/mod.io/`，通常展开为 `C:/Users/Public/mod.io/`。目录布局可作为线索：

```text
<公共用户目录>/mod.io/<游戏编号>/mods/<模组编号>/content/tf3_mcp_bridge/bridge.script.lua
```

只读查找示例：

```powershell
$tf3ModRoot = Join-Path $env:PUBLIC 'mod.io'
if (Test-Path -LiteralPath $tf3ModRoot) {
    rg --files --hidden $tf3ModRoot | Select-String '[/\\]content[/\\]tf3_mcp_bridge[/\\]bridge\.script\.lua$'
}
```

这只是常见入口，不保证每台机器都相同。不要把某位用户的磁盘、Steam ID、游戏编号或模组编号写死到通用配置。找不到时根据已有配置与日志定位其他根目录；仍有缺失再询问用户。

### 3.3 用本次游戏日志确认来源

在实际 Steam 目录的 `userdata/<Steam 用户>/3493540/local/` 下定位本次游戏日志，核对修改时间及本次会话。搜索：

```text
tnj_tf3_ai_bridge
ModHubMod
modHubId
source: mod.io
```

将日志中的来源、模组 ID 和候选下载目录对应。检查同一用户 `local/mods/` 中是否存在同 mod ID 本地副本；它可能遮蔽下载版。源码目录和 staging 发布副本也不能仅凭存在就认定是已加载文件。

存在多个用户、候选或副本时，不选搜索结果第一项，不自动删除冲突副本；用当前日志判别，证据不足时说明歧义并询问必要信息。

### 3.4 区分路径与加载证据

最终 MCP 路径是包含 `bridge.script.lua` 的 **`content/tf3_mcp_bridge`** 目录。记录候选来源，配置后再以实时版本、接收器代次和模式交叉验证，最后执行只读请求。文件存在、版本号相同或心跳在线都不能单独证明选择了正确副本。

## 4. 配置本地 MCP 服务

参考 [.mcp.example.json](../../.mcp.example.json)，将占位路径替换为实际绝对路径，再写入客户端要求的 JSON/TOML 等格式：

```json
{
  "mcpServers": {
    "tf3": {
      "command": "uv",
      "args": ["--directory", "<项目绝对路径>/server", "run", "tf3-mcp"],
      "env": {
        "TF3_MCP_TRANSPORT": "no_gui",
        "TF3_MCP_NO_GUI_MOD": "<已验证安装目录>/content/tf3_mcp_bridge"
      }
    }
  }
}
```

| 配置 | 含义 |
|---|---|
| `command` | 客户端能启动的 uv；若客户端 PATH 不含 uv，使用现场找到的绝对路径 |
| `--directory` | 源码内的 server 目录，不是模组目录 |
| `TF3_MCP_TRANSPORT` | 当前为 no_gui，不回退旧 file |
| `TF3_MCP_NO_GUI_MOD` | 实际安装模组的 content/tf3_mcp_bridge |
| `TF3_MCP_DIR`（可选） | 本地账本与协调文件目录；不能为了连接删除原有未知请求记录 |
| `TF3_UI_LANGUAGE`（可选） | zh-CN、en 或 auto |

仅修改 tf3 服务，保留其他客户端设置。个人路径、实际配置、作者信息和凭据只保存在本地；公开仓库仅保留占位模板。

## 5. 确认接收器模式与加载状态

### 安装件保护（强制）

- “连接 MCP”“配置服务”“验证连接”或“排查连接问题”不授权修改游戏安装件。此范围内禁止将项目 `mod/`、发布暂存目录或其他副本复制、同步、覆盖到 mod.io 下载目录，也禁止运行会改写下载模组的安装器。
- 找到项目源码不代表找到游戏实际加载的模组。通过修正 MCP 路径解决指向错误，不通过覆盖下载模组使其匹配源码；不得为消除副本冲突自动删除或改写任何副本。
- 仅当用户已明确授权修改安装件以修复或更新模组，且已确认实际目标、问题及所需变更时，才能进入安装件修改流程。已有明确授权无需重复申请；缺少授权时先完成只读诊断，说明具体原因和拟修改内容，再请求授权。
- 修改前在目标模组目录外备份原文件，核对是否存在未决请求，保留其证据。使用当前受支持安装流程及发布配置，禁止直接用默认关闭接收器的开发源码覆盖正式包；修改后核对文件、实际加载版本并重新只读验收。
- mod.io 更新可能替换本地修改。优先采用正式发布更新；不得将本地修改描述为官方下载包原有内容或已发布修复。

| 模式 | 用途 |
|---|---|
| userdata | mod.io 下载版默认，使用原生 userdata 邮箱 |
| demand | 本地开发模组，使用新建的一次性 Lua 资源 |
| indexed | 有限诊断兼容模式，不作长期默认 |

安装器 auto 是模式选择规则，不是第四种模式。正式下载包应已启用 userdata，正常首次连接不需要重写下载件。开发源码的接收器默认值不等于发布包配置，不直接覆盖正式包。

确有接收器缺失/过旧且任务包含修复时，再阅读 [下载版连接](../reference/MODIO_CONNECTION.md) 和安装器 `scripts/install_no_gui_diagnostic.py --help`，使用当前备份、编译检查与原子替换流程。下载版不使用 demand 绕过资源发现限制。

- 改客户端配置或 Python 服务：重连/重启 MCP 服务。
- 改游戏 Lua 接收器：需要重新加载启用模组的地图，磁盘更新不替换内存代码。

首次尚未进入地图或心跳失效时，不能靠失效 MCP 连接自举读档。请用户进入地图；涉及保存/读档时遵循已有授权与 [读档指南](../reference/LOAD_GAME.md)，不丢弃当前进度。

## 6. 做最小只读连接验收

1. 发现工具并调用 `bridge_status`，核对新鲜心跳、版本、代次、模式、会话、主机、pending 及切换状态。工具出现仅证明服务能启动。
2. 若状态要求绑定，读取 `bind_no_gui_session` 的当前 schema，使用刚取得的精确 `expected_session`，再独立确认状态与地图。绑定不是清除未知写入的手段。
3. 确认实时 `readBatchVersion` 支持后，调用 `read_planning_data`：

```json
{
  "requests": [
    {"command": "get_game_state", "arguments": {}},
    {"command": "get_map_info", "arguments": {}},
    {"command": "list_towns", "arguments": {"limit": 3}}
  ]
}
```

逐项检查 `executed/ok` 与子结果 `available/complete`。这不是原子快照；下一轮详情必须使用本轮真实 ID。批处理能力缺失时先说明版本不匹配，按当前工具能力选择受支持的只读查询，不自动重装或重发失败批次。详见 [只读批处理](../reference/READ_BATCH.md)。

4. 再检查未决状态。交付实际来源/版本、已验证路径、接收器模式、地图/玩家身份及成功读取项目；个人路径仅在本地交付，不写入公开验证记录。分别标明未知与未测试项。

成功只读往返证明当前连接可用，不证明所有施工接口或长期运行已验收。首次连接不通过试建、贷款、购车、变速或恢复监控“测试连接”。

## 7. 常见阻碍与处理

| 现象 | 下一步 |
|---|---|
| 客户端没有 TF3 工具 | 检查服务启动错误、uv、依赖和源码路径，重连目标服务 |
| 无心跳或心跳过期 | 检查是否进入地图、模组激活和本次日志，不发送写入 |
| 心跳新鲜但请求不通 | 检查目录和实际加载来源，尤其下载版是否误用 demand |
| 实时版本与磁盘不同 | 检查副本遮蔽、内存旧代码和是否需要重载 |
| 会话变化 | 核对当前地图、主机、未决状态，按受支持流程绑定，作废旧实体及预览 |
| 超时、部分成功或结果未知 | 保留原请求 ID、回执与账本，定向查原请求和现场；不重发、不删 pending、不靠重启/换通道清锁 |

只有有依据且受支持的修复才继续。没有安全路径时，报告具体阻碍、已完成阶段和恢复条件，不循环尝试同一失败命令。

## 8. 后续使用

后续优先复用已验证本地路径；更新、移动、来源切换或失联时重新发现。每次工作确认当前会话和地图，不能复用其他地图 ID。

- 查询与规划：[路线规划](ROUTE_PLANNING.md)、[只读批处理](../reference/READ_BATCH.md)。
- 授权施工：[操作协调](OPERATION_COORDINATION.md)、[逐项预览/施工/验证](../reference/CONSTRUCTION_PROJECT.md)。
- 线路与验收：[货运装卸](../reference/CARGO_LOADING.md)、[载具投运](CARRIER_ACCEPTANCE.md)。
- 用户明确要求监控后：[监控提示词](MAIN_CITY_DEVELOPMENT_MONITOR_PROMPT.md)。

已安装 `tf3-mcp` skill 的 Agent 可直接调用该 skill；未安装 skill 也可按本文完成连接。skill 不随 MCP 握手自动安装，MCP 初始化的简短说明不等于已阅读本指南。

可复制给 Agent：

> 阅读 docs/guides/FIRST_CONNECTION.md，自动发现游戏实际加载的 TF3 AI Bridge 模组，检查依赖并配置本地 MCP 服务。保留其他配置和未知请求记录，完成当前地图的只读连接验证，报告实际加载来源、版本及任何阻碍。不要施工、改速或恢复监控。
