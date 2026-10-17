# TF3 文档导航

- [通信方式与接收器模式：no_gui、file 及 request.lua 边界](reference/TRANSPORT_CHANNELS.md)


本项目用于 Transport Fever 3。文档按“发展决策 → 执行流程 → 接口参考 → 历史证据”分类。最后整理：2026-10-06。

## 按任务阅读

| 要做什么 | 先读 | 再读 |
|---|---|---|
| 修改已有产业、车辆发车、城市建筑、日期环境和库存 | [世界操作接口](reference/WORLD_ACTIONS.md) | 47项目录、39项执行适配器、8项明确阻断；预览/备份/单次提交/读回 |
| 镜头跟随、地图标记、界面引导、声音、性能与运输诊断 | [原生界面与诊断接口](reference/NATIVE_EXTRAS.md) | 30个工具、GUI/引擎分流、能力检测与未实机验收范围 |
| 使用独立 Citaro G1 高速及10倍装载测试车型 | [Citaro 测试车型](reference/CITARO_TEST_MODEL.md) | 原版资源引用、自动价格及加载/购车边界 |
| 使用独立800 km/h中型城市道路测试限速 | [高速测试道路](reference/SPEED_TEST_ROAD.md) | 资源加载、与原版差异及施工验收边界 |
| 修改单车速度、噪音、污染、舒适度倍率，了解其他可改属性 | [载具属性接口](reference/VEHICLE_MODIFIERS.md) | 原生来源合成、备份、未决读回及尚未实机验收的边界 |
| 首次连接 MCP、发现下载模组目录或排查连接 | [Agent 首次连接完整指南](guides/FIRST_CONNECTION.md) | [通信模式](reference/TRANSPORT_CHANNELS.md)、[下载版连接](reference/MODIO_CONNECTION.md) |
| 一次发送工程，由接收器逐项预览、提交和验收 | [接收器工程批处理](reference/CONSTRUCTION_PROJECT.md) | 支持范围、进度续作、预算及未知结果保护 |
| 自动线路配色、默认色、逐节涂装及图片源包 | [载具外观 v2](reference/VEHICLE_APPEARANCE_V2.md) | 启停、预算、配置保护与资源加载边界 |
| 读取载具外观、单车/多车/线路统一配色 | [载具改色接口](reference/VEHICLE_APPEARANCE.md) | 遮罩限制、逐车回执与未决保护 |
| 一次读取多项游戏数据 | [接收器只读批处理](reference/READ_BATCH.md) | 白名单、返回语义、大小及时间预算 |
| 了解 AI 如何通过 MCP 读取、规划和操作游戏 | [AI 控制游戏的完整过程与实现逻辑](guides/HOW_AI_CONTROLS_TF3.md) | 架构、通信、道路、建筑、线路、车辆及结果验证 |
| 在既有道路上增加电车轨道或公交车道 | [道路升级](reference/ROAD_UPGRADE.md) | 结构预览边界、车道权限及限定实测 |
| 读取城市声誉、运送、噪音、加成、幸福感、交通和污染 | [城市面板概览](reference/TOWN_OVERVIEW.md) | 字段可用性、原生统计口径与实测限制 |
| 货运规划收尾、维护分流、交付时效与批量执行 | [运营预测与执行契约](guides/CARGO_PLAN_FINALIZATION.md) | [统一规划流程](guides/PLANNING_WORKFLOW.md) |
| 建造或复用总部 | [总部建设指南](guides/HQ_ACCESS_DIAGNOSTIC.md) | [设施接口](reference/FACILITY_SUPPORT.md#总部专用接口) |
| 规划与验收集合共用仓库 | [主仓库共库检查](strategy/TRANSPORT_CARGO_CONNECTIONS.md#主仓库共库检查) | [集合批量流程](guides/GROUPED_CONSTRUCTION_WORKFLOW.md#主仓库共库验收) |
| 检查船坞、码头与渔场往返航路 | [船舶往返航路检查](guides/SHIP_ROUTE_CHECKS.md) | [集合航路验收](guides/GROUPED_CONSTRUCTION_WORKFLOW.md#船舶往返航路去重) |
| 规划生产点旁的四设施集合 | [四设施生产模板](guides/PRODUCTION_COLLECTION_TEMPLATE.md) | [集合选址与共用](guides/GROUPED_CONSTRUCTION_WORKFLOW.md)、[六设施城市模板](guides/CITY_HUB_DEPOT_TEMPLATE.md) |
| 每轮监控城市、供货、公交、载具和仓库并按授权处理 | [每轮监控清单](guides/MONITORING_WORKFLOW.md) | [人口公交](guides/POPULATION_BUS_MONITOR.md)、[操作协调](guides/OPERATION_COORDINATION.md) |
| 判断交通设施是否需要仓库、货站或客运接驳 | [配套矩阵与完整运输链](strategy/TRANSPORT_CARGO_CONNECTIONS.md#各类建筑配套矩阵) | 运输任务判断、配套数量与验收清单 |
| 比较各类交通建筑的站址、接驳和维护布局 | [交通设施选址指南](strategy/TRANSPORT_FACILITY_SITING.md) | [执行手册](guides/AGENT_PLAYBOOK.md)、[批量选址](reference/SITE_SELECTION.md) |
| 为一个城市制定分期发展计划 | [城市发展策略](strategy/city-development-strategy.md) | [发展方案模板](strategy/DEVELOPMENT_PLAN_TEMPLATE.md) |
| 调查地图、输出全局或局部规划图 | [执行手册](guides/AGENT_PLAYBOOK.md)第 2～3 节 | [规划与可视化接口](reference/PLANNING_TOOLS.md) |
| 建造、改路、建线路或购车 | [项目执行规则](../AGENTS.md)、[执行手册](guides/AGENT_PLAYBOOK.md) | 对应接口说明与[操作协调](guides/OPERATION_COORDINATION.md) |
| 扩建仓库、港口或其他设施 | [设施接口](reference/FACILITY_SUPPORT.md) | 策略中的升级预留要求 |
| 天然平地不足时平整局部用地 | [地形平整接口](reference/TERRAIN_FLATTEN.md) | [规划与前置工序](guides/PLANNING_WORKFLOW.md#找不到天然平地时的地形平整) |
| 快速比较停靠点、仓库或车站的位置 | [批量选址](reference/SITE_SELECTION.md) | [局部布局与卡片](reference/PLANNING_TOOLS.md) |
| 编辑城市需求货物种类 | [城市货物需求接口](reference/TOWN_CARGO_NEEDS.md) | 原生参数、读回和验证边界 |
| 查询或办理游戏贷款 | [贷款接口](reference/LOAN_SUPPORT.md) | 发展方案中的资金安排 |
| 接取通知中的机遇任务 | [补贴任务接口](reference/SUBVENTIONS.md) | [操作协调](guides/OPERATION_COORDINATION.md) |
| 调查停靠点崩溃、部分施工或超时 | 执行手册第 4、6、9、10 节 | [停靠点历史诊断](../STREET_STOP_INTERFACE.md) |

## 目录职责

- `strategy/`：发展顺序、生产布局、运输与仓储平衡、分期方案模板。经营建议与当前地图事实分开记录。
- `guides/`：会话确认、授权范围、预览与提交、读回验证、操作协调和异常处置。
- `reference/`：工具参数、调用顺序、结果解释、支持范围与验证边界。

根目录 [README](../README.md) 提供首发使用说明、安装入口与功能概览；[AGENTS](../AGENTS.md) 是 agent 的入口规则。工具签名以 [server.py](../server/src/tf3_mcp/server.py) 为准；游戏侧行为还须核对当前部署的桥接与存档。

## 如何判断文档中的结论

| 标记或内容 | 可以据此判断 | 不能据此判断 |
|---|---|---|
| 接口已实现 | 当前源码存在对应入口 | 当前游戏已加载同版本，或已完成实机写入验证 |
| 历史只读核对／测试记录 | 指定时间、环境下的观察结果 | 当前地图仍有相同实体或数值 |
| 预测、经营建议、升级预留 | 候选布局和需要核对的条件 | 原生碰撞通过、准确后期需求或收益保证 |
| `built`、静态 `verified` | 对应接口的回调／读回结果 | 完整运输周期、重载或长期模拟安全 |

规划与图片卡片已实现；跨规划、施工和补贴任务的统一调度、共享运力／预算预留尚未实现，当前由执行者按操作协调文档安排。不要把建议流程写成工具已有能力。

## 文档维护约定

1. 通用约束集中在执行手册，参数与能力边界集中在接口说明；其他文档链接引用，避免复制后不一致。
2. 新能力分别注明“引入版本”“验证日期与范围”；最低版本不等于必须安装的精确版本。
3. 当前计划使用新采集的数据；历史案例保留日期、已验证事项和未解决事项。地图变化后重新调查。
4. 移动文档时同步修正根目录与文档内部链接；示例坐标、金额和实体编号必须注明来源或为占位符。
5. 只改文档不连接游戏。文档检查验证内部链接与接口名称，不以此替代实机验证。


## 开发记录与历史复盘

[首次公开发布前的开发记录](README_LEGACY.zh-CN.md)仅供技术追溯，其中的内部版本号、临时加载命令和现场步骤不是发布版本列表或当前操作指南。

本次集合经验：[集合规划与施工复盘（2026-10-05）](guides/COLLECTION_REVIEW_20261005.md)，包含模板串组、入口适配、验收边界、固定地图存档槽及代码优化优先级。

全图规划与恢复经验：[三门峡规划施工复盘（2026-10-03）](guides/SANMENXIA_PLANNING_REVIEW_20261003.md)。包含联合选址、小批运输链验证、崩溃检查遗漏、存档隔离和验收分层。
