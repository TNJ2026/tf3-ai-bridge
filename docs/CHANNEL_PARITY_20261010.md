# 原文件通道与新通道功能差异审计（2026-10-10）

## v32 实现更新

用户选择先实现有明确路径的迁移。当前已补充具名工具新通道路由、组件选择/分页、整体冻结规划快照、2～32 站复杂线路编辑、持久车辆批次，以及自动接取适配与显式只读监控。离线回归及有限实机验收已完成：两站重排与恢复、停运标记批次及重启防重放、两轮只读采样、自动接取dry-run。实际接取新任务、批次购车/出售及全部复杂站序组合未实测。详细范围、参数限制和未实现项见 [NO_GUI_MIGRATION.md](reference/NO_GUI_MIGRATION.md)。

监控和自动接取未开启，历史工程脚本未重放。普通拆除、任意 eval、自动读档、联动多模块以及全部旧参数不在本轮完成范围内。以下保留 v31 审计原文作为迁移前证据，不再作为 v32 功能缺失清单。

## v31 历史审计

本次只读检查当前源码与既有验收记录，没有连接游戏、运行旧脚本、修改地图或恢复监控。这里检查的是功能迁移完整性；此前“本轮无其他待执行项”仅指有限实机验收清单，不表示新旧接口、参数及自动化工作流完全等价。

## 统计口径

- `server.py` 声明86个 MCP 工具（包括条件注册的 `run_lua`、本地规划工具和两种通道入口）。
- 新通道主机白名单为9个基本读取命令、95个引擎侧命令，以及独立 `save_game`，共105个命令名。引擎侧集合也包含只读和预览，不能称为95项施工功能。
- Lua 中静态提取99个 `commands.<name>` 赋值。15个名称不直接出现在新白名单，但其中7个已有预览/提交替代，`configure_facility`部分替代，`ping`有新的状态入口；不能把15个全部计为缺失。
- 机器清单：`output/channel_parity_20261010/inventory.json`。不把动态 Lua/eval 的任意组合视为可以用有限接口总数穷举，也不据命令名存在推定参数等价或实机全部通过。

## 尚未完成的迁移

| 类别 | 源码事实与影响 | 已有替代／建议 |
|---|---|---|
| 1. 旧具名 MCP 工具的统一路由 | `server.py:206` 的 `_call` 仍直接调用 `Bridge.call`，后者写旧 `request.lua`。例如直接调用旧 `get_game_state`、`buy_vehicles` 不会自动走 no_gui。 | 新通道已支持的功能须显式使用 `send_no_gui_request` / `read_no_gui_result`。若要旧工具无缝复用，需要适配层；不能只替换传输后沿用旧参数、超时和重试语义。 |
| 2. 整体规划快照、路由快照及缓存刷新 | `get_planning_snapshot`、`get_route_snapshot`未入新白名单。`capture_planning_snapshot`、`plan_rail_connection`的现场刷新，以及`map_cache_control`的start/refresh仍依赖旧桥接。 | 分页地形、实体查询已有，但未组装成原快照契约。纯离线全局/局部规划、选址、报表可复用已有合规快照；旧快照不能冒充当前现场。 |
| 3. 通用组件选择及集合分页 | 新`get_entity`只接受`id`，不接收旧`components`参数；`get_component_collection`未接入。默认组件列表不能替代任意受支持组件和长集合的完整分页。 | 已有设施、库存、乘客/货物等专用读取以及`list_map_entities`分页，覆盖若干用途，但未达到旧通用查询接口的参数范围。 |
| 4. 普通拆除与孤立站点修复 | `bulldoze`、`repair_orphan_street_stop`未接入。 | `preview_test_removal/commit_test_removal`仅允许当前会话由本通道建成并确认的受限对象：无依赖测试边或自有空测试仓库。不能据此拆除既有设施、任意车站或道路。 |
| 5. 原自动化工作流 | `subvention_autoaccept`仍绑定旧`_subvention_call → _call`。`fullmap_batch/fullmap_lines/fullmap_fleet`、`monitor_city_health`、`fleet_observe`、`ship_route_checks`仍存在直接旧桥接/eval依赖。 | 单次机遇查询与预览/接取、单车购置/分配、专用库存查询已接入；完整自动接取、工程清单执行、全图诊断和船舶成组验路尚不能原样运行。离线编译/预算/清单函数可保留，在线调度需迁移与独立验收。 |
| 6. 通用 Lua/eval 与临时原生诊断 | 旧`run_lua`（需环境开关）/`eval`没有新通道入口。原来借此完成的自定义线路整体替换、特定原生查询、自由提案等没有自动获得支持。 | 当前新通道是明确白名单，应按实际需要提取专用、有界、可预览和读回的操作；不建议为“补齐”直接放开任意代码执行。已有单接点/车辆运动读取不等于任意端点、所有交通模式的通用验路。 |
| 7. 自动读档及部分跨重载对账 | v31仅接入保存，没有`load_game`；旧`save_reload_guard.py`仍以旧eval调用`app.loadGame`。新`get_prospection_operation`未接受旧`tracking_receipt`参数，缺少该接口的跨Lua状态恢复输入。 | 保存文件写入已实机通过，读档未接入，也未以新测试文件完成读档验收。勘探可读当前列表，但不能把列表查询当作已恢复原操作回执。 |

## 已有功能但参数／操作范围缩小

| 功能 | 当前差异 |
|---|---|
| 线路配置 | 已有创建/删除、货品装载、单一装载比例、强制卸货、额外等待、站台选择。只支持2～8站简单线路；有waypoints或alternativeTerminals时拒绝。没有专用接口增删/重排现有线路站序、改名/颜色，也不提供每货品分别设置不同maxLoad的输入。旧具名`create_line`的color参数未迁移；其他复杂修改以前主要依赖eval。 |
| 车辆 | 每次购置、分配、出售仅1台，购车与上线分两步；出售须实际在库。`send_to_depot`不接受`sell_on_arrival`，返库自动出售未接入。批量可由上层逐项编排，不应认为“完全不能批量”；原工作流尚需迁移。 |
| 设施配置 | 原`configure_facility(parameters, modules)`的多参数/多模块同次配置，缩为单模块或单数值参数预览，再提交。可以逐项完成的配置不等于缺失；需要联动原子修改的组合仍未覆盖。模块删除原实现也不支持，不能计为迁移倒退。 |
| 道路、车站和车库选项 | 已有直路、曲线道路/轨道、电车道、路段升级、站点和车库。旧`build_road`的任意长via列表、snap_radius、max_segment_length等未完整迁移；新`preview_network`仅最多3个中间点且不接受中间节点连接。站点新接口须先解析edge，不接受旧坐标就近选路参数；建筑自定义name、自动face_towards、connect、street_type等旧便捷参数未全部暴露。可由显式规划/分段施工替代部分功能，仍不能宣称参数等价。强制碰撞绕过不应作为待恢复目标。 |
| 查询筛选 | `list_vehicles(line=...)`未接入；可在结果完整时本地筛选。`list_facilities(mine_only=False)`未接入，当前专用列表为自有设施。新接口分页大小等有更严格边界。 |

## 不应再列为“未实现”

道路、铁路、有轨电车基础设施；水运与航空设施/载具；线路创建、车辆购置分配及货品/装载配置；总部、仓库、设施单项模块升级；工业建设、城市货品需求修改、勘探、贷款；地形平整；机遇单次接取；货物/乘客身份读取；暂停与1/2/4倍速；无GUI保存，均已有对应新通道接口。

其中具名替代映射包括：

- `build_road → preview_road + commit_road`（曲线路网另有`preview_network + commit_network`）。
- `upgrade_road/build_street_stop → preview_road_upgrade/preview_street_stop + commit_edge_edit`。
- `build_depot/build_station/build_rail_station → preview_depot/preview_station/preview_rail_station + commit_structure`。
- `accept_subvention → preview_subvention + commit_subvention + get_subvention_operation`。
- `configure_facility → preview_facility_module/preview_facility_parameter + commit_facility`（部分范围）。

以上是实现范围，不是所有车型、参数组合、地图和长期模拟均已验证。现有验收证据见`UI_OPERATION_ACCEPTANCE_20261009.md`。铁路同一乘客下车按用户要求跳过；长期原生缓存回收、无限运行/建设和所有参数组合未验证；v31保存写入通过而测试存档读档未验。这些与“接口未接入”分别记录。

## 建议补齐顺序

先迁移组件分页与整体快照契约，再做具名工具路由和旧工作流适配；随后补复杂线路、联动设施配置、受控普通拆除及跨重载恢复。自动读档单独实施、单独验收。保留新通道未知结果不重发、会话/实体重解析、明确预览提交和读回规则，不能通过绕过白名单或放宽旧脚本执行来代替迁移。

此次只新增审计文档和本地机器清单，没有修改产品代码；没有提交或推送Git。
