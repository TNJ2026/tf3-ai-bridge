# Transport Fever 3 AI Bridge

[English](README.md) | **简体中文**

连接 AI 助手与《Transport Fever 3》，支持地图分析、运输规划及游戏操作。

![Transport Fever 3 AI Bridge](mod/tf3_mcp_bridge/_metadata/0.png)

项目包含游戏端模组和本地 Python MCP 服务。你需要自行配置兼容 MCP 的 AI 客户端；模组不内置 AI 模型，也不包含模型服务订阅。

## 功能

- 查询城市、产业、供需、库存、线路、车辆和财务。
- 采集地图与地形快照，筛选设施位置，规划运输连接。
- 导出 HTML、PNG、SVG 和 JSON 规划报告。
- 通过对应接口预览、提交并读回设施、道路、线路和车辆操作。
- 查询机遇、贷款及运营状态；自动化功能需单独配置。

具体接口的能力和验证边界见[文档导航](docs/README.md)。预览通过、实体建成和长期运营稳定是不同阶段，不能相互替代。

## 工作原理

```text
AI 客户端 → MCP（标准输入输出）→ Python 服务 → 本地文件桥接 → 游戏模组 → 游戏引擎
```

模组通过 GUI 环境中的 `app.saveUserdata` / `app.loadUserdata` 与服务交换请求、响应和心跳文件。默认桥接目录：

```text
<Steam>/userdata/<Steam ID>/3493540/local/tf3_mcp/
```

## 环境要求

- 已安装 Transport Fever 3，并载入启用本模组的存档。
- Python 3.11 或更高版本，以及 `uv`。
- 支持 MCP 标准输入输出传输的客户端。
- 自动安装脚本面向 Windows / Steam；其他环境的安装流程尚未验证。

## 语言与路径

规划报告和卡片支持英文与简体中文。在 MCP 服务的环境变量中设置 `TF3_UI_LANGUAGE=en`、`zh-CN` 或 `auto`，然后重启服务。自动选择依次读取进程语言设置（`LC_ALL`、`LC_MESSAGES`、`LANG`）与系统区域设置，无法识别时回退英文；不检测游戏语言。已保存的规划保留生成时的显示语言，更换语言后需重新生成规划。卡片初始使用浏览器／宿主语言，收到报告后采用报告语言。

原生实体名称、资源 ID 和自定义标题保持原样。游戏坐标面板采用中英文提示；此次兼容不代表所有工具说明和文档均已翻译。

设施选址与铁路规划的显示文字也遵循该语言设置。快照／规划 JSON 导入和恢复配置支持带 BOM 或不带 BOM 的 UTF-8。`TF3_RECOVERY_CONFIG` 支持用户目录与环境变量展开；读取配置不会启用恢复或监控。

`TF3_MCP_DIR` 可指定桥接目录，支持 `~` 和环境变量展开。`TF3_PLANNING_FONT` 可指定报告图片字体文件；含中文名称时应选支持中文字形的字体。程序会尝试常见 Windows 字体及可用的 Linux／macOS 字体作为回退。

英文显示、Unicode 传输及含空格／非 ASCII 字符的路径已有离线测试。英文游戏已实测查询、地形采集、报告生成、仓库原生预览、保存验收和速度切换读回；测试地图现金为零，尚未验证付费施工和车辆运营。英文 Windows 未单独测试。详见[英文兼容验证](docs/reference/ENGLISH_COMPATIBILITY.md)。

## 在 Agent 中快速开始

在能够访问本地文件并配置 MCP 连接的 AI Agent 中打开本项目，然后在聊天中输入以下提示词。由 Agent 处理配置和工具调用，你只需描述目标。

### 1. 配置并连接游戏

> 阅读本项目文档，帮我安装并配置 Transport Fever 3 AI Bridge，检查本地依赖和 MCP 连接。需要我在游戏中启用模组、载入存档时告诉我，然后验证连接是否正常。

### 2. 了解当前地图

> 分析当前地图、城市需求、已有运输线路和资金情况，找出主要供给瓶颈和可以改善的地方。

### 3. 规划一个项目

> 为承德规划一条供给路线，优先利用附近产业和现有设施，估算建设成本与运营费用。先展示方案，不要施工。

将“承德”替换为当前地图上的城市。也可以要求规划公交线路、选择仓库位置，或优化已有运输网络。

### 4. 执行已审阅的方案

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

发布源文件位于 `mod/tf3_mcp_bridge/`，源目录名称保留以兼容工具。将完整目录复制到游戏用户目录的 `staging_area/tnj_tf3_ai_bridge/`，再通过主菜单 **Mod Hub → My Mods** 校验和上传。

`_metadata/0.png` 为封面，`_metadata/modinfo.json` 保存作者与介绍。发布副本不进入 Git；本地 MCP 服务仍需另行安装。

`exports/`、现场调查记录、日志和测试临时目录不随源码发布。历史文档对这些文件的引用可能在公共仓库中不可用。

- [文档导航](docs/README.md)
- [规划工具](docs/reference/PLANNING_TOOLS.md)
- [历史版本与接口说明](docs/README_LEGACY.zh-CN.md)
- [官方模组发布指南](https://wiki.transportfever3.com/doku.php?id=modding:general:publishing)


**实机验收：** 已完成记录中的有限操作场景；铁路同一乘客下车按用户要求暂时跳过。固定翼部分为空载试飞，长期缓存回收、无限运行和所有车型／货品组合未获证明。详见[操作验收记录](docs/UI_OPERATION_ACCEPTANCE_20261009.md)。实验性[无 GUI 通道](docs/HEADLESS_TRANSPORT_20261009.md)需主动启用，源码默认配置中关闭。
