# Transport Fever 3 AI Bridge

[English](README.md) | **简体中文**

连接 AI 助手与《Transport Fever 3》，支持地图分析、运输规划及游戏操作。

![Transport Fever 3 AI Bridge](mod/tf3_mcp_bridge/_metadata/0.png)

项目包含游戏端模组和本地 Python MCP 服务。你需要自行配置兼容 MCP 的 AI 客户端；模组不内置 AI 模型，也不包含模型服务订阅。

## 功能

- 查询城市、产业、供需、库存、线路、车辆和财务。
- 通过[城市面板概览接口](docs/reference/TOWN_OVERVIEW.md)读取声誉、运送、噪音、奖励/加成、幸福感、交通和污染，逐项标明数据可用性与已知限制。
- 采集地图与地形快照，筛选设施位置，规划运输连接。
- 导出 HTML、PNG、SVG 和 JSON 规划报告。
- 通过对应接口预览、提交并读回设施、道路、线路和车辆操作。
- 查询机遇、贷款及运营状态；自动化功能需单独配置。

具体接口的能力和验证边界见[文档导航](docs/README.md)。预览通过、实体建成和长期运营稳定是不同阶段，不能相互替代。

## 工作原理

推荐使用 `no_gui` 通道，按接收器模式通过 Lua 资源文件或原生 userdata 邮箱传入请求，通过游戏日志返回结果与接收器状态。旧 `file` 通道已在只读实测失败后移除，请使用 `no_gui`。详见[通信方式、接收器模式及 request.lua 边界](docs/reference/TRANSPORT_CHANNELS.md)。

```text
AI 客户端 → MCP（标准输入输出）→ Python 服务 → 一次性请求资源 → 游戏模组 → 游戏引擎
                                      ↑                           ↓
                                      └────── 游戏日志中的响应 ────┘
```

`demand` / `indexed` 模式的请求资源位于已安装模组的 `content/tf3_mcp_bridge/no_gui/`；本地请求账本和协调文件默认位于：

```text
<Steam>/userdata/<Steam ID>/3493540/local/tf3_mcp/
```

新版发布包已内置默认启用的接收器。加载模组后，在 MCP 服务中设置 `TF3_MCP_TRANSPORT=no_gui`，并将 `TF3_MCP_NO_GUI_MOD` 指向已安装模组的 `content/tf3_mcp_bridge` 目录。`no_gui` 表示无需手动操作桥接 GUI 面板，游戏窗口仍正常运行。本地 MCP 服务仍需另行配置；旧下载版接收器修复见下文。mod.io 下载版无法发现运行中新增的请求文件，请先阅读[下载版 userdata 配置与验收状态](docs/reference/MODIO_CONNECTION.md)。配置流程见[no_gui 通道说明](docs/NO_GUI_TRANSPORT_20261009.md)。

## 环境要求

- 已安装 Transport Fever 3，并载入启用本模组的存档。
- Python 3.11 或更高版本，以及 `uv`。
- 支持 MCP 标准输入输出传输的客户端。
- 自动安装脚本面向 Windows / Steam；其他环境的安装流程尚未验证。

## 语言与路径

规划报告和卡片支持英文与简体中文。在 MCP 服务的环境变量中设置 `TF3_UI_LANGUAGE=en`、`zh-CN` 或 `auto`，然后重启服务。自动选择依次读取进程语言设置（`LC_ALL`、`LC_MESSAGES`、`LANG`）与系统区域设置，无法识别时回退英文；不检测游戏语言。已保存的规划保留生成时的显示语言，更换语言后需重新生成规划。卡片初始使用浏览器／宿主语言，收到报告后采用报告语言。

原生实体名称、资源 ID 和自定义标题保持原样。游戏坐标面板默认隐藏，保留坐标采样逻辑和中英文显示实现；此次兼容不代表所有工具说明和文档均已翻译。

设施选址与铁路规划的显示文字也遵循该语言设置。快照／规划 JSON 导入和恢复配置支持带 BOM 或不带 BOM 的 UTF-8。`TF3_RECOVERY_CONFIG` 支持用户目录与环境变量展开；读取配置不会启用恢复或监控。

`TF3_MCP_DIR` 可指定本地账本与协调文件目录，支持 `~` 和环境变量展开。`TF3_PLANNING_FONT` 可指定报告图片字体文件；含中文名称时应选支持中文字形的字体。程序会尝试常见 Windows 字体及可用的 Linux／macOS 字体作为回退。

## 在 Agent 中快速开始

按以下步骤下载模组和项目文件，在支持本地文件访问及 MCP 连接的 Agent App 中创建项目，再配置服务并开始规划。

### 1. 下载并激活模组

前往以下模组页面下载 **Transport Fever 3 AI Bridge**，并在开始新游戏或载入存档之前，在模组列表中激活它。

模组 URL：<https://mod.io/g/transportfever3/m/transport-fever-3-ai-bridge-3-ai>

### 2. 下载并解压项目

打开 [GitHub Releases](https://github.com/TNJ2026/tf3-ai-bridge/releases)，选择对应版本，在 **Assets** 中下载 **Source code (zip)** 项目压缩文件，并解压到本地文件夹。

### 3. 在 Agent App 中创建项目

打开 Agent App，新建项目，并选择上一步解压后的项目文件夹路径（包含 `README.md`、`server/` 和 `mod/` 的目录）作为项目目录。

### 4. 配置并连接游戏

先读[Agent 首次连接完整指南](docs/guides/FIRST_CONNECTION.md)：自动发现实际模组目录、配置服务、核对加载来源并完成只读验证。

> 我已下载并激活游戏模组。阅读本项目文档，帮我安装并配置本地 MCP 服务及 no_gui 通道，检查本地依赖、接收器和 MCP 连接。游戏载入后，验证连接是否正常。

### 5. 了解当前地图

> 分析当前地图、城市需求、已有运输线路和资金情况，找出主要供给瓶颈和可以改善的地方。

### 6. 规划一个项目

> 为承德规划一条供给路线，优先利用附近产业和现有设施，估算建设成本与运营费用。先展示方案，不要施工。

将“承德”替换为当前地图上的城市。也可以要求规划公交线路、选择仓库位置，或优化已有运输网络。

### 7. 执行已审阅的方案

> 按刚才审阅的方案和预算施工，完成基础设施、线路配置及方案内的车辆采购。验证实际装货、交付和维护情况，报告阻碍和未完成事项。

运营后，可以继续输入：

> 检查新线路是否存在缺货、拥堵、货物过期或资金风险，并提出优化建议。

## 操作流程与当前限制

先检查连接及当前地图，再读取目标对象。世界修改按“调查 → 备份 → 当前预览 → 单次提交 → 独立读回”执行；超时或结果未知时先对账，不自动重发。

当前已有路口新增分支及多设施生成端口联合提交保留保护性限制。原生崩溃根因尚未全部解决，不能把几何预览通过当成提交安全保证。示例和历史文档里的实体编号不能直接用于当前存档。

执行前阅读 [AGENTS.md](AGENTS.md) 和[操作手册](docs/guides/AGENT_PLAYBOOK.md)。文档中的监控或历史施工流程不构成当前任务的授权。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `mod/tf3_mcp_bridge/` | 游戏模组、发布元数据和封面 |
| `server/` | Python MCP 服务及 `tf3-bridge` 命令行工具 |
| `scripts/` | 安装、规划、诊断和执行工具；部分为历史实验 |
| `config/` | 规划模板与配置 |
| `docs/` | 接口说明、操作指南和历史记录，以中文为主 |
| `.mcp.example.json` | 可移植的客户端配置示例 |

## 开发与测试

```powershell
cd server
uv sync --extra test
cd ..
$env:PYTHONPATH = 'server/src;scripts'
server/.venv/Scripts/python.exe -m pytest server/tests scripts/tests -q
```

最新全套测试与编译检查结果见[当前验证记录](docs/TEST_VALIDATION_20261010.md)。离线测试不代表原生游戏行为或存档长期模拟稳定性已验收。

## 发布与文档

更新模组信息、准备或清理发布副本、校验或上传前，先阅读[模组发布流程](docs/guides/PUBLISHING.md)。发布副本须排除 `content/tf3_mcp_bridge/no_gui/` 运行时文件，清理时在模组外保留请求证据，之后重新进行游戏原生校验。

发布源文件位于 `mod/tf3_mcp_bridge/`，游戏本地发布副本位于用户目录的 `staging_area/tnj_tf3_ai_bridge/`。通过游戏主菜单 **Mod Hub → My Mods** 校验和上传；按当前发布约定，不生成或上传 ZIP。

**每次升级同时递增 `mod.json` 的整数修订号 `revision` 和脚本中的桥接版本 `BRIDGE_VERSION`。** 模组介绍显示桥接版本号，更新说明标题也按桥接版本号组织，不按日期。同步源码和本地发布副本；两种版本号不要求数值相同。实际基线以源码、发布副本及上一版发布记录为准。

完整版本同步、更新说明和上传检查规则见[模组发布流程](docs/guides/PUBLISHING.md)。更新说明简洁描述修复的问题或新增功能。

`_metadata/0.png` 为封面，`_metadata/modinfo.json` 保存作者与介绍。发布副本保持正式 userdata 接收器启用，不直接用默认关闭接收器的开发源码覆盖。上传前运行 `python scripts/check_mod_package.py "<本地发布目录>" --require-receiver`，再进行游戏原生校验。本地 MCP 服务仍需另行安装和配置。

`exports/`、现场调查记录、日志和测试临时目录不随源码发布。历史文档对这些文件的引用可能在公共仓库中不可用。

- [文档导航](docs/README.md)
- [规划工具](docs/reference/PLANNING_TOOLS.md)
- [官方模组发布指南](https://wiki.transportfever3.com/doku.php?id=modding:general:publishing)
