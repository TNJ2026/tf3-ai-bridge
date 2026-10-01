# TF3 MCP Bridge

通过 **Agent → MCP → 模组** 控制《狂热运输3》(Transport Fever 3)。

文档分类入口见 [docs 导航](docs/README.md)，包括发展策略、执行指南、接口参考与历史案例。实时规划和建造前请先阅读 [agent 入口](AGENTS.md) 与 [规划、建造及防崩溃执行手册](docs/guides/AGENT_PLAYBOOK.md)。下文各版本章节保留历史能力说明，实际执行还需核对当前接口与手册中的验证边界。

```
Agent ──MCP(stdio)──> server/ (Python) ──文件──> mod/tf3_mcp_bridge (game script) ──> 游戏引擎
```

游戏脚本既没有网络库也没有 `io`。唯一能用的文件接口是 GUI 环境里的 `app.saveUserdata` / `app.loadUserdata`，所以模组在 `guiUpdate` 里轮询，通过游戏的用户数据目录 `<Steam>\userdata\<id>\3493540\local\tf3_mcp\` 和 MCP Server 交换文件。Server 会自动找到这个目录，也可以用环境变量 `TF3_MCP_DIR` 指定：

| 文件 | 写入方 | 内容 |
|---|---|---|
| `request.lua` | Server | `{"id", "cmd", "args"}`；空闲时是没有 `id` 的占位请求 |
| `response.lua` | 模组 | `{"id", "ok", "result" \| "error"}` |
| `heartbeat.lua` | 模组 | 约每秒一次：游戏时间、Lua 环境探测结果、最近错误 |

每个文件的内容都是 `function data() return { hex = "<十六进制编码的 JSON>" } end`，这样两边都不依赖游戏怎么转义字符串。

## 目录

- `mod/tf3_mcp_bridge/` — 游戏模组。`content/tf3_mcp_bridge/bridge.gs.lua` 注册 game script，`bridge.script.lua` 是全部逻辑（JSON、userdata 通信、命令分发）。引擎侧脚本会热重载；GUI 侧（通信循环所在）要重新载入存档才生效。改脚本时要整体替换文件，否则游戏可能读到改了一半的内容。
- `server/` — Python MCP Server（`mcp` 2.x）和命令行测试工具 `tf3-bridge`。
- `scripts/install_mod.ps1` — 把模组以目录联接方式装进 Steam 的 `userdata\<id>\3493540\local\mods`。
- `.mcp.json` — Claude Code 的 MCP 配置。

## 使用

1. 安装模组：`powershell -ExecutionPolicy Bypass -File scripts\install_mod.ps1`
2. 启动游戏 → 新游戏（或读档）→ **添加模组** 里激活 **TF3 MCP Bridge** → 进入存档。
3. 检查连通：
   ```
   cd server
   uv run tf3-bridge status
   uv run tf3-bridge ping
   uv run tf3-bridge get_game_state
   ```
4. 在 Claude Code 里打开本目录，`.mcp.json` 会注册 `tf3` MCP Server。

## MCP 工具

全局／局部规划及 HTML、PNG、SVG 导出见 [规划工具说明](docs/reference/PLANNING_TOOLS.md)（桥接 0.11.0）。

规划工具完成后直接显示 MCP Apps 图片卡片（全局全图、局部裁切），支持缩放；完整 HTML 由用户点击卡片链接打开，不自动打开。

贷款接口新增于桥接版本 0.10.0；调用流程、校验及实机验证边界见 [游戏贷款接口](docs/reference/LOAN_SUPPORT.md)。

| 工具 | 说明 |
|---|---|
| `capture_planning_snapshot` | 无需车站的全图／局部只读调查，保存可复用快照 |
| `plan_global_development` | 重点城市、邻城候选、产业来源、供给瓶颈及分期发展 |
| `plan_local_development` | 设施占地、升级预留冲突、陆路候选走廊及仓储核算 |
| `export_planning_report` | 导出带图层和缩放的 HTML，以及 PNG、SVG、JSON |
| `bridge_status` | 心跳、连接状态、Lua 环境探测 |
| `ping` | 走一遍完整的请求/响应链路 |
| `get_game_state` | 日期、游戏时间、速度、余额、贷款 |
| `get_finances` | 余额、贷款 |
| `get_loans` | 原生贷款报价、冷却、现有合同、月供与剩余本金 |
| `preview_loan` | 只读预览借款或还款，生成 60 秒一次性令牌 |
| `commit_loan` | 使用预览令牌单次提交原生借还款事件 |
| `get_loan_operation` | 查询提交结果，核对合同与余额，不重发交易 |
| `get_subventions` | 原生补贴任务（待接受/进行中/完成/失败）：金额、货物、目标、截止天数；可评估现有线路运力与货源 |
| `accept_subvention` | 按 uid 单次接受补贴，等同游戏内"接受"按钮；发送前复核条款，同一 uid 不重发（0.12.0） |
| `subvention_autoaccept` | 在 MCP 进程内按规则轮询自动接受补贴，默认 dry_run 只记录决策；日志写入桥接目录 `subvention_autoaccept.json` |
| `list_towns` | 城镇列表 |
| `list_stations` | 车站组（线路站点引用的对象）：名称、位置 |
| `list_depots` | 车库：载具类型、位置、库内车辆 |
| `list_lines` | 线路：站点顺序、车辆 |
| `list_vehicles` | 车辆状态（可按线路筛选） |
| `list_vehicle_models` | 当前年份可买的车型：价格、容量、速度 |
| `get_entity` | 按 id 查看实体组件 |
| `get_map_info` | 全图边界、尺寸、地形分辨率、气候，以及全部城镇/工业的位置 |
| `list_map_entities` | 按实体类型分页读取全图，包含其他玩家实体；返回总数和下一页位置 |
| `get_terrain_grid` | 分页采样全图或指定区域的地面高度、水域标记 |
| `get_terrain_tile` | 查询 256 米地形瓦片的实体、原始高度与刷涂数据可用性 |
| `get_component_collection` | 分页读取水域顶点、模型实例、原始高度、库存规则等集合 |
| `get_map_data` | 列出或分页读取生物群系、森林、河流等数据图 |
| `create_line` / `delete_line` | 按车站组顺序建线路 / 删除线路 |
| `buy_vehicles` | 在车库买车，可直接分配到线路 |
| `assign_vehicles` | 把车辆分配到线路 |
| `sell_vehicles` / `send_to_depot` / `set_vehicle_stopped` | 卖车 / 回库（可到库即卖）/ 停车或发车 |
| `set_game_speed` | 设置模拟速度（0 = 暂停） |

| `run_lua` | 在游戏引擎脚本环境里执行 Lua（仅当 `TF3_MCP_ALLOW_EVAL=1`），用于探索 API |

带有 `mine_only` 参数的列表默认只返回玩家自己的实体；`mine_only=false` 可看全部。

### 铺路（桥接版本 0.6.0）

使用 `list_street_types` 查道路模板，`find_nearby` 查附近节点，再调用 `build_road`。
`start` / `end` 支持 `{ "node": 79500 }` 或 `{ "x": -850, "y": 1600 }`；
`via` 是按顺序经过的点列表。坐标单位为米。

```python
build_road(
    start={"node": 79500},
    end={"x": -892.9, "y": 1665},
    street_type="town/town_old_small",
    max_segment_length=25,
    preview=True,
)
```

- `preview=True` 只评估，不建造：返回费用 `cost`、阻挡物 `blocking`、游戏错误 `messages`、
  实际点位与吸附情况 `points`、分段路线 `path`、以及考虑碰撞选项后的 `buildable`。
  核对后用相同参数和 `preview=False` 建造；建造时重新检查当前地图。
- 起终点默认在 5 米内吸附到道路节点；铁路节点不参与。`snap_radius=0` 关闭吸附；
  单个点的 `snap` 可覆盖半径。途经点默认不吸附，除非指定 `node` 或 `snap`。
- 默认跟随地形。点位提供 `z` 时，与该点相邻的直线段插值高度；吸附时也检查高度差。
- `max_segment_length` 范围 10–200 米，默认 50；单次最多 128 个路径点、512 段。
- 默认拒绝碰撞建筑、道路和设施；`allow_collisions=True` 可放行碰撞，但不能绕过致命错误。
  建造结果包含 `built`、实际新增 `edges` / `nodes`；失败返回 `reason`。

当前支持普通地面道路及已有道路节点连接。尚不支持自动切开路段建立路口、自动桥隧或曲线。
修改后需重新载入存档以确保游戏使用新版脚本；已连接的 MCP 客户端需重启服务刷新参数定义。
实机只读检查可运行 `server/.venv/Scripts/python.exe scripts/verify_road_preview.py`；
结果存于 `road_preview_validation.json`，其中 `activeUpdated` 标明是否直接使用了运行中的新版。

### 更换已有道路类型（桥接版本 0.6.1）

`upgrade_road(edge, street_type, preview=True)` 调用官方 `replaceSegment`，保留路段走向、高度、
切线和两端路口节点。`edge` 可从 `find_nearby` 或 `list_map_entities(kind="BASE_EDGE")` 获取。

```python
# 第一步：查看参数预览
upgrade_road(edge=8778, street_type="town/town_old_medium", preview=True)
# 第二步：提交同一改造，可带上预览返回的 fromType 检查道路类型是否已变化
upgrade_road(edge=8778, street_type="town/town_old_medium", preview=False,
             expected_street_type="country/country_old_small")
```

此版本的预览为 **参数与结构预览**：返回 `fromType`、`toType`、`nodes` 和 `positions`。
`validation="structural_only"`、`costAvailable=false` 表示未检查费用和碰撞；
不对含删除路段的提案调用可能触发引擎断言的预览 API。不能把参数预览成功视为可建造保证。
提交时由游戏校验整份替换提案，`ignoreErrors=false`，不先单独拆除旧路。

成功返回 `applied=true`、`changed=true`、`verified=true` 和实际替换后的 `edges`。
路段 ID 可能变化，应使用返回的新 ID；请求相同类型返回 `noChange=true`，不提交命令。
若 `applied=true` 但 `verified=false`，需先检查地图，不要自动重试。

当前只支持单条普通地面道路，不支持铁路、桥隧、附带站点等对象的路段或设施自带道路；
不支持修改走向和高度。`expected_street_type` 只检测类型变化，不是完整地图快照校验。
需重新载入存档并刷新 MCP 服务，才能直接使用新增的 `upgrade_road` 工具。
`scripts/verify_road_upgrade.py` 可隔离加载新脚本进行实机参数预览，不提交改造。

### 通用设施配置与建造（桥接版本 0.9.0）

新增 `list_facility_resources`、`list_facilities`、`get_facility_config`、
`configure_facility`、`build_facility` 和 `commit_facility`。
支持现有仓库、港口、各类车站/车库/维护站的原生模块查询与允许的配置修改；
新建通过复制现有设施布局实现。配置默认仅结构预览，单独的一次性令牌提交才施工。
完整覆盖表、原生模板与模块拆除限制、测试状态见 [设施接口说明](docs/reference/FACILITY_SUPPORT.md)。

### 货运火车站（桥接版本 0.7.0）

`build_rail_station` 新建贯通式货运站，使用非电气化基础轨道，站台按游戏年代选择外观。

```python
build_rail_station(x=6200, y=2000, tracks=2, length=160,
                   rotation=0, specialization="universal", preview=True)
# 核对费用、碰撞及位置后，用 preview=False 提交相同参数。
```

- `tracks`：1–4 条股道；`length`：80、120、160、240、320 米。
- `rotation`：逆时针角度，0 度时股道沿地图 Y 轴；`name` 可指定站名。
- `specialization`：`universal` 通用、`bulk` 散货、`liquid` 液体、`flatbed` 平板或 `goods` 商品。
- 默认 `preview=True`，返回费用与阻挡物。`preview=False` 才实际建造。
- 成功返回 `construction`、`stations`、`stationGroups`，以及分类的 `railPorts` / `roadPorts`。
  端口包含节点、位置和所在边的切线；切线沿该边 node0 到 node1 的方向，不保证朝向站外。
- **不自动铺设外部铁路或道路**。`externalConnectionsBuilt=false` 始终明确这一点；
  `verified` 只检查站点和铁路端口是否生成，不代表列车已有可达路径。

测试覆盖参数校验、模块布局、建造返回与端口分类、碰撞拒绝。当前实机验证为预览，
包括双股道160米站和四股道320米方案的道路碰撞检测；尚未进行实机建造验收。
重新载入存档并重启 MCP 服务后，新工具生效。

### 全图读取（桥接版本 0.5.1）

先调用 `get_map_info` 获取地图边界和城镇、工业坐标，再调用
`list_map_entities(kind="BASE_EDGE", offset=0, limit=100, snapshot="new")` 分页读取道路。
支持的类型：`TOWN`、`INDUSTRY`、`CONSTRUCTION`、`TOWN_BUILDING`、`BASE_NODE`、
`BASE_EDGE`、`STATION`、`STATION_GROUP`、`VEHICLE_DEPOT`、`TRANSPORT_VEHICLE`、
`SIM_PERSON`、`LINE`、`WATER_MESH`、`MODEL_INSTANCE_LIST`、`ASSET_GROUP`、
`SIM_CARGO`、`STOCK_LIST`、`TERRAIN_TILE_BRUSH`。此接口不按所有者过滤，每页 1–500 项，按 ID 排序；
按 `nextOffset` 继续，直到 `hasMore=false`。`total` 是该类型索引的总数，不受旧接口
2,000 项上限影响。道路、水域和渲染模型分别使用专用路网、水域及空间索引；
装饰物、货物、库存、刷涂组件通过全实体索引筛选，避免引擎拒绝通用组件遍历。
模型/装饰实体只返回实例数量，再用 `get_component_collection` 读取
`MODEL_INSTANCE_LIST` 的 `fatInstances` 或 `thinInstances`，取得模型路径、位置/变换等字段。

全量遍历建议首请求传 `snapshot="new"`，后续页带上返回的 `snapshot` 标识及 `nextOffset`。
该模式固定实体 ID 列表，期间新增实体不会插入，已删除或不再具有该组件的条目返回
`{id=..., missing=true}`；组件字段仍为实时值，并非整个存档的原子快照。
完成后调用 `release_map_snapshot(snapshot=...)`。快照保留 300 秒，最多缓存 4 份，
单份最多 250,000 个 ID；超限、失效或类型不符会明确报错。重新载入存档会使旧标识失效。
不传 `snapshot` 时沿用实时偏移分页，实体增删可能导致重复或遗漏。
原有 `list_*` 和 `find_nearby` 的查询范围、数量限制保持不变。

`get_entity` 会显式读取常用组件及嵌套记录的公开字段，包括库存规则、站台、线路停靠点、
车辆配置，支持二维/三维/四维向量、包围盒和矩阵。字段映射来自游戏 build 40408 自带类型定义。
字段不可用时返回 `_unavailableFields`，尚未支持展开的嵌套 userdata 返回
`_unavailable="opaque_userdata"`，深度超过限制返回 `_truncated="max_depth"`。
每个普通集合最多展开 2,000 项；较大的顶层集合用 `get_component_collection` 分页，
每页最多 1,024 项，返回原始 Lua `key` 和 `value`。偏移从 0 开始，原始键不改变。
集合元素内部仍有深度和长度限制，所以这些接口不等于完整存档导出。

#### 地形、水域和地图数据图

- `get_terrain_grid` 默认从地图最小坐标开始，以 64 米间隔采样，按行排列（x 先递增）。
  固定网格参数并传 `nextOffset` 继续；`mode="surface"` 返回含地形对齐的高度，
  `mode="base"` 读取基础地形。间距最小 1 米，粗采样不等于保留所有地形细节。
- `get_terrain_tile(tile_x=-28, tile_y=-28)` 查询对应的 256 米瓦片；合法范围从
  `get_map_info.bounds` 除以 256 推导，包含负坐标，最大瓦片坐标不包含地图外边界。
  用返回的实体 ID 分页读取 `TERRAIN_TILE_HEIGHTMAP.vertices` 可取得原始整数高度；
  这些整数不是米，物理高度优先使用 `get_terrain_grid`。
- `list_map_entities(kind="WATER_MESH")` 返回水域网格，顶点、深度、索引、轮廓可通过
  `get_component_collection` 分页读取。索引值保持游戏原值，不自动改成 Python/Lua 的索引方式。
- `get_map_data()` 列出数据图名称和分辨率；指定 `layer` 后按行分页读取原始值。
  本次存档实测有 9 张 448×448 数据图，包括 `biome*`、`forest_mask`、`river_mask`。
  这些是地图数据图，不是游戏渲染后的纹理像素。
- `TERRAIN_TILE_BRUSH` 可查询刷涂材质索引；当前存档全实体扫描结果为 0，
  因此只验证了无数据分支，不能宣称非空刷涂纹理已验证。

2026-09-30 实测：18 类实体查询均可运行；抽样字段、9 类数据图、树木模型路径及变换、
水域顶点读取成功；一个瓦片的 4,225 个原始高度值已连续分页校验，无漏项或重复。
没有导出整个存档或逐项校验全图所有实体，实时模拟也不保证跨请求快照一致性。

升级后重新载入存档使 GUI 脚本生效，并重启 MCP 服务以注册新工具。
`scripts/verify_map_fix.py` 可通过现有桥接在独立 Lua 环境验证磁盘上的新版只读处理器，
不会升级正在运行的 GUI 桥接。需使用 server 的 Python 环境，并在自动发现不可用时设置 `TF3_MCP_DIR`。

## 开发

- 测试（不需要游戏，用 lupa 在 Lua 5.2 里跑真实的 `bridge.script.lua` 和模拟 API）：`cd server && uv run pytest`
- 游戏日志：`<Steam>\userdata\<id>\3493540\local\crash_dump\stdout.txt`，模组日志前缀 `[tf3_mcp_bridge]`。
- 官方 API 定义：`<TF3 安装目录>\api\tealdef\`。
- 更新嵌套字段映射：`server\.venv\Scripts\python.exe scripts\generate_component_schema.py "<TF3 安装目录>\api\tealdef"`。
  生成器只替换 Lua 中标记的字段映射块，并原子替换文件；运行游戏不依赖本地类型定义文件。
- `scripts/probe_map_layers.py` 保存底层查询路径的能力诊断；部分通用枚举失败是引擎限制，
  不是对应新工具失败，新工具使用已验证的替代索引。
- `scripts/audit_map.py` 逐页检查 18 类实体及全图 64 米地形采样，输出 `map_coverage_snapshot_audit.json`。
  `--live` 用于对照实时偏移分页；`--isolated-load` 在独立 Lua 环境验收磁盘上的处理器，
  不替换当前 GUI 桥接。模型/装饰物只遍历实体与实例数量，不展开每一个模型实例。

### 完整数据导出

`scripts/export_map_data.py` 导出全图原生 4 米地形、所有模型实体的全部 fat/thin 实例、
所有地图数据图的全部格子。此脚本会暂停模拟，并在成功或异常退出时尝试恢复原速度；
仅在用户同意暂停后执行。它通过现有 eval 桥接加载独立只读处理器，不要求重新载入存档。

输出位于 `exports/map-时间/`：

- `map.sqlite`：原始数据；表为 `terrain_tiles`、`model_entities`、`map_layers`、`map_cells`、`metadata`。
  `*_zlib` 列为 zlib 压缩的 UTF-8 JSON，可用 `json.loads(zlib.decompress(blob))` 读取。
- `manifest.json`：来源信息、数量、完整性校验结果、原速度/恢复结果和 SHA-256。
  只有 `status="complete"` 才表示三部分导出全部完成。

完成后执行 `scripts/materialize_map_export.py exports/map-时间` 生成便携文件：

- `terrain_base_4m.f32.gz`：去掉瓦片共享边界后的完整高度网格，gzip 压缩、小端 float32，单位米。
  行内 x 向东递增，行间 y 向北递增；尺寸和最小角坐标记录在 manifest 中。
  数据是基础地形，不包括非永久的地表对齐修改；原始整数高度保留在 SQLite 中。
- `layer_*.f32.gz`：每张数据图的完整格子，小端 float32，按行排列、x 先递增。
  原始 JSON 数值保留在 SQLite 中；这些文件不代表渲染纹理像素。
- `model_instances.jsonl.gz`：每行一个实例，包含实体 ID、实例序号、模型路径，以及位置/旋转/缩放
  或完整变换矩阵。矩阵 `columns` 按列存储；fat 实例还保留此前帧的变换。
  实测游戏矩阵列采用 0–3 索引，读取器已兼容；若运行时没有 `transf0`，会明确记录在
  `_unavailableFields` 中，当前变换 `transf` 仍完整保存。

导出会验证模拟时间不变、模型实体集合不变、数据库可解压读取，并在生成高度网格时校验所有
瓦片接缝与每块瓦片的原始高度换算。结果不是整个游戏存档的二进制副本。
若模型阶段失败而地形与数据图已完成，可用 `--resume-models exports/map-时间` 重新采集全部模型；
这会再次暂停并恢复模拟，清单中的 `captureSessions` 分别记录各部分采集时间，不声称来自同一帧。

### 批量铁路选线（桥接版本 0.7.1）

优先调用 `plan_rail_connection(start_construction, end_construction)`，传入两座车站的 **CONSTRUCTION ID**。
它只读、不暂停、不施工：一次引擎请求取得全部空闲轨道端口、走廊地形与道路/建筑/模型包围盒，
本地比较端口组合、7 种横向绕行和 3 种设计高度，按长度、桥隧和土方代价排序。
模型型车库也算障碍，不再仅依靠 CONSTRUCTION/TOWN_BUILDING 组件判断。

返回 `candidates`、采样路径、桥隧长度、坡度、曲率和 `stats`。候选只是近似选线，`buildable=null`；
施工前必须刷新端口并进行原生预览，施工后检查站内轨道之间的双向 TRAIN 寻路。
不要把采样检查当作碰撞保证，也不要忽略未知碰撞强制施工。
没有候选时返回诊断，不自动反复调用游戏；可扩大走廊或进行更细的路径搜索。
当前采用有限的曲线候选搜索，不能保证找到所有可行线路或全局最优解。

可直接使用脚本（当前运行的旧版 mod 可加 `--hotload`，一次只读 eval 加载本地实现）：

```powershell
server/.venv/Scripts/python.exe scripts/plan_rail_route.py --start 120586 --end 116328 --hotload --output route_candidates.json
server/.venv/Scripts/python.exe scripts/plan_rail_route.py --snapshot route_candidates.snapshot.json --output route_replay.json
```

重放同一快照不访问游戏。快照不跨施工复用：实体编号、道路和地形都可能变化。
新增 MCP 工具需 MCP 进程重启后列出；mod 重载后可原生调用 `get_route_snapshot`，无需 hotload。

### 地图缓存与分阶段规划（0.8.0）

`plan_rail_connection` 现在使用全图缓存，顺序为：两点直线 → 建成区与零散建筑绕行 → 地形与既有路网通过分析 → 曲线/坡度验证。
绕行采用 A*，城镇范围由带有 town 归属的建筑包围盒合并并向外留 120 米缓冲；
起终点所在建成区允许进出，但其中的建筑仍是障碍。道路在避让阶段不作为建筑处理，
在高程阶段分别尝试上跨、下穿，双向传播坡度约束以预留坡道距离。无解时返回原因，不强制施工。
曲线与地形为采样近似，包围盒可能过于保守，不承诺找到全局最优路线；最终仍需原生预览与通行验证。

缓存内容包括地形采样、道路/铁路节点和曲线、建筑/车库包围盒、城镇建筑归属、当前空闲车站端口。
首次全量读取，之后轮询实体与地形修订号：对象仅传回变化项，删除对象移出缓存；
地形修订号不变则复用网格，有地形变化时重采样整个网格（尚非地形瓦片级增量）。
每五分钟强制全量对账。全图网格上限 100000 点，大地图需增大 spacing。
数据只在当前进程会话内复用，磁盘快照不自动当作新会话的实时地图。

- `map_cache_control(action="start", start_construction=..., end_construction=...)`：启动每 15 秒更新。
- `action="status"`：查看缓存年龄、对象数、轮询状态和错误。
- `action="refresh"`：立即查询修订号并同步。
- `action="invalidate"`：清除缓存，后台轮询会立即重新读取；切换存档时也应使用它。
- `action="stop"`：停止轮询。MCP 进程退出时轮询一并停止。

本进程的施工/拆除/道路升级使缓存失效并唤醒后台刷新；手动改动在下次轮询发现。
这不是逐帧变更订阅。缓存命中规划不查游戏，施工前必须重新同步并执行原生预览。
MCP 进程启动后可运行新工具；现有旧版游戏 mod 可用脚本临时加载当前只读采集实现：

```powershell
server/.venv/Scripts/python.exe scripts/watch_map_cache.py --start 120586 --end 116328 --hotload --once
server/.venv/Scripts/python.exe scripts/watch_map_cache.py --start 120586 --end 116328 --hotload
```

第二条保持轮询，Ctrl+C 停止。桥接客户端采用操作系统文件锁，避免后台缓存与其他客户端覆盖同一请求文件。

### 道路接入验证（0.8.1）

铺路完成后检查每个接入点的 CAR/TRUCK 双向寻路，路径必须直接经过原路、接入节点、新路，
绕行其他道路不算接通。失败时，对原有尽头的空车道配置先单独清理，再用原生 replaceSegment
刷新新路段，最后再次检查。保留非空自定义转向配置；健康路口无需重建。
替换后按节点对重新查询路段编号，返回有效的新编号。

`built=true` 仅表示路已存在；`verified=true`、`complete=true` 才表示接入点验证通过。
若刷新失败或验证不可用，返回连接诊断并保留已建路，禁止重复执行同一次铺路。
预览不清理配置、不刷新道路。曲线道路脚本也复用此接入处理。
