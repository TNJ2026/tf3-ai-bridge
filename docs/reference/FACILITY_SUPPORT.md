# 设施查询、配置与建造接口（始于桥接 0.9.0）

2026-10-01。资源目录与现有设施已经在运行中的 build 40408 存档只读核对；仓库扩建通过结构预览，预览前后配置相同。没有在正式存档提交建筑替换或新建。

## 覆盖范围

当次实机目录包含 588 个 construction、26 个 metaConstruction 和 131 个 module。construction 包含大量城市建筑、产业和装饰资源，不能把目录数量当作可升级设施数量。

| 对象 | 配置/升级 | 新建 |
|---|---|---|
| 仓库 | 查询全部真实槽位，增设或替换匹配货类的模块 | `build_warehouse` 从零新建通用仓库；也可复制已有布局 |
| 港口 | 增设匹配槽位的码头、泊位、入口等模块；已占槽位仅允许原生声明可替换者 | 复制已有港口布局，显式指定水面高度 |
| 公路车站、货运站 | 模块增设、允许的替换；原生标记可修改的参数 | 复制已有布局；原有 `build_station` 仍可从零建设 |
| 铁路车站 | 通用模块与参数接口 | 复制已有布局；原有 `build_rail_station` 仍可从零建设 |
| 机场、直升机设施 | 原生提供的槽位和可修改参数 | `build_helipad` 从零预览直升机停机坪；机场仍需复制已有布局 |
| 公路、铁路、电车、船舶车库 | 只开放原生声明可修改的参数/槽位 | 复制已有布局；原有 `build_depot` 保留 |
| 公路、铁路、水上维护站 | 同上；没有槽位不代表接口漏掉升级 | 复制已有布局 |
| 道路 | 原有 `upgrade_road` | 原有 `build_road` |
| 路边停靠点 | 不进入普通建筑替换流程 | 必须使用 `build_street_stop` |
| 总部（桥接 0.12.2） | 查询参数、模块与槽位；暂不开放扩建或搬迁 | `build_headquarters` 使用原生主楼模板，随后 `commit_facility` 单次提交 |
| 工业、城市建筑、装饰、桥隧与轨道段 | 目录可查询；不通过此次通用设施接口修改 | 需要各自专用接口，未新增支持 |

当次历史存档读回 11 处自有设施：1 个仓库、1 个港口、3 个公路站、3 个车库/船坞、3 个维护站。其中前 5 处提供模块槽位；后 6 处没有原生可修改槽位或参数。实体编号仅使用实时查询结果。

**边界：** `build_facility` 使用现有设施作为完整布局来源，尚不能直接执行全部 26 个 metaconstruction 的原生模板工厂。总部、通用仓库及原生直升机停机坪已有专用从零新建入口；没有现有实例、且专用建造工具不覆盖的其他设施，仍需先有模板实例。未开放模块拆除、非默认模块变体、跨资源更换建筑或任意改写内部参数。

### 直升机停机坪专用新建（0.12.4）

`build_helipad(x,y,z,rotation=0,name="")` 使用当前安装的 `::/stations/air/helipad.con`，核对原生 updateScript、1950 年可用限制、公司许可、干燥地面及重复设施，生成无模块的原生参数。严格几何预览后，`commit_facility` 单次提交并读回设施配置；终端和货物覆盖由批量脚本另行读取。36×38 米原生占地，90×90 米双停机坪及接驳预留是估算。原生入口 snap point 局部 `(0,-25)`，不自带冻结道路边。

批次流程及验收边界见 [BATCH_CONNECTIONS_HELIPADS.md](../../scripts/BATCH_CONNECTIONS_HELIPADS.md)。当前实机只进行了只读预览，尚未施工、建立航线、购买车辆或验证长期模拟。

### 通用仓库专用新建（0.12.3）

`build_warehouse(x, y, z, rotation=0, name="", module_count=4)` 只读原生几何预览，不需要已建仓库；通过 `commit_facility` 单次提交。`module_count` 仅支持1或4，对应预计500或2000库容。按当前年份选择原生通用仓库元模板，检查可用性、模板脚本、初始模块、模块类型和原生公司许可；拒绝无效坐标、水域和位置上已有仓库。

原生工厂为定义 `data()` 的Lua资源，不能直接require到桥接全局。接口按已核对的 `warehouse.script.lua` 初始化与编码复现初始槽位 `(0,3)`；4模块使用原生大型模块4格间距，增加 `(4,3)、(0,7)、(4,7)`。保留原生模块metadata、updateScript和默认variant。使用现有严格碰撞预览，包括可完整识别的树木清理；未知碰撞、意外拆迁和不完整碰撞信息阻止提交。

提交重新检查模板、许可、玩家/世界、时效、重复仓库和碰撞；配置读回后再通过 `WAREHOUSE.stockList` 检查原生库存总容量。`externalConnectionsBuilt=false`：新接口不接路、不建货站/线路、不购车。72×88米初期占地和192×192米16模块预留为原生尺寸估算，并非升级原生预览。

验证：仓库、原有设施、总部及批量脚本共53项离线测试通过。徐州方案4座2000库容仓库通过当前地图原生几何预览，无碰撞/致命错误；仅涉及已识别树木清理。证据在 `exports/supply_warehouse_20261002/warehouse_interface_preview.json`。尚未实机提交、验证收发货、长期模拟或重载，不能据预览宣称已建成或稳定。

MCP工具需刷新连接，常规运行时需加载新版桥接。`scripts/batch_warehouses.py --disk-bridge` 可在旧版现有引擎eval内隔离加载新版磁盘接口；提交时重新预览并在同一实例消费新令牌，不跨请求复用令牌，不写全局、不自动重载游戏。源码改变或提交未知时停止。见 [批量脚本说明](../../scripts/BATCH_WAREHOUSES.md)。

## 规划时预留升级空间

### 总部专用接口

`build_headquarters(town, x, y, z, rotation=0, name="")` 使用原生主楼模板只读预览；`z` 必须明确。位置距目标城镇中心不超过1000米，且该城镇是最近城镇。预览与提交均核对公司许可、玩家是否已有总部及现场状态。

取得 `preview_token` 后，使用 `commit_facility` 单次提交；建后独立验证配置和入口连接。总部可通过 `list_facilities`、`get_facility_config` 查询，通用克隆、扩建及搬迁接口未开放。

选址、备份、原生预览和入口验收统一见[总部建设指南](../guides/HQ_ACCESS_DIAGNOSTIC.md)。

## 调用流程

1. `list_facility_resources(kind, search, offset, limit)` 查询资源；kind 是 `construction`、`metaConstruction` 或 `module`。分页上限 200，按 `next_offset` 继续。原生内部资源的负年代哨兵表示基础资源年代未定义，应结合模板或模块判断，不能据此判定游戏里不可建造。
2. `list_facilities()` 重新解析当前存档的自有设施。
3. `get_facility_config(entity)` 读取完整 native params、4 列变换矩阵、现有模块、槽位、类型上限、道路/轨道接点和兼容模块。`cloneable` 与 `configurable` 分开报告。
4. `configure_facility(entity, parameters={}, modules=[...])` 仅预览配置。每项模块指定 `slot` 与完整 `resource` 名称。或者使用 `build_facility(source_entity, x, y, z, rotation=0, name="")` 预览复制布局。
5. 在施工前存档和施工授权已落实的前提下，使用返回的 `preview_token` 调用 `commit_facility`。默认查询/预览不会施工；没有 `preview=False` 捷径。

参数数值使用原生 `numbers` 枚举；没有 numbers 时使用 **1 起始**的选项编号。只接受 `postConstructionModifiable=true` 的现有参数。模块保留资源原生 metadata/updateScript；未改动的参数通过 `params_native:asTable()` 完整复制，不通过会截断的通用 JSON 视图回写。

令牌只保存在引擎当前脚本实例的局部内存，60 秒内一次有效。提交先消费令牌，再重新比较配置、位置/角度、冻结节点/边及外部接点；日期回退或跨年也使令牌失效。脚本重载导致令牌失效；不要在重载存档或切换会话后复用预览。`rail_eval.py` 每次隔离加载脚本，因此不同调用间不能交接令牌。

## 预览与提交限制

### 结果如何用于决策

| 结果或现象 | 应如何理解 | 下一步 |
|---|---|---|
| 资源目录中存在该建筑 | 能查询资源，不等于接口支持新建或升级 | 查覆盖表、当前实例及专用工具 |
| `cloneable` 与 `configurable` 不同 | 复制布局与修改原设施是不同能力 | 按实际操作选择工具 |
| 无兼容空槽位／无可修改参数 | 当前原生布局没有可用的对应配置入口 | 不猜槽位或改内部参数；比较其他布局 |
| `structural_only=true` | 参数、槽位和模块结构经过检查 | 占地碰撞与施工后关系仍待验证 |
| 令牌失效 | 预览的时效或目标状态已变化 | 重新调查、重新预览；不修改旧令牌 |
| 提交超时或读回不匹配 | 操作结果未知，可能部分生效 | 核对实际配置、新 ID 与外部连接，不重复提交 |

### 新建和升级后的验收

- **配置预览仅做结构校验**，报告 `structural_only=true`、`collision_checked=false`。原生建筑替换可能移除道路边，调用 `makeProposalData` 预览存在已知断言风险，不能将结构预览宣称为碰撞通过。
- 新建使用原生几何预览，并在提交时重做；任何碰撞、意外拆除、不可读取的碰撞信息都会阻止提交。
- 提交只执行一次原生命令，`ignoreErrors=false`，不自动重试。使用官方 `createProposalReplaceConstruction` 保留既有关系，不自行拆除后重建。
- `built` 仅表示回调接受；`verified` 仅表示位置和参数/模块读回匹配。未确认结果、超时、部分成功都必须重新核对地图。
- 不自动接道路、建线路、购车或验证换乘。连通性、线路挂接及长时间模拟仍需单独检查。尤其不能将本次测试视为 `MakePersonCapacityData` 历史断言已修复。
- 配置提交和复制新建尚未在隔离存档实机完成验证；首次验证应使用可丢弃的测试存档，不在正式存档试未知布局。

验收至少分别记录：参数／模块是否匹配、当前实体与外部道路／轨道是否相连、原有线路站点是否仍有效、货类和换装是否符合需求，以及观察到的实际服务。扩仓后还需更新可用库容与升级预留图，不能把新增库容记成新增运输吞吐。

布局示意和升级预留使用[规划工具](PLANNING_TOOLS.md)；分期能力核算使用[发展方案模板](../strategy/DEVELOPMENT_PLAN_TEMPLATE.md)。

## 验证与加载

`server/tests/test_facilities.py` 在真实 Lua 桥接源码上模拟原生 API，覆盖参数保留、模块校验、限额/所有权、一次提交、严格错误检查、配置失效、日期回退、未知碰撞/拆除、提交读回，以及 MCP 引擎路由和失败后的缓存失效。

`scripts/check_facility_interface.lua` 只读查询实机目录和设施，并为第一个有适配空槽位的仓库执行结构预览，再读回检查；不会调用 `commit_facility`。

新增 MCP 工具需刷新/重启服务；游戏侧需重新加载更新后的桥接脚本。正式使用前先保存进度，再自行重新载入启用了本 mod 的存档。此次没有自动重载用户存档。


## 直升机场购机与维护接口（2026-10-03）

`build_heliport(x,y,z,rotation=0,name="")` 预览原生 `::/stations/air/heliport.con`，再由 `commit_facility(preview_token)` 单次提交。与 `build_helipad` 的小型停机坪区别是原生布局包含购机机库和自动维护服务：停放容量 5，维护池 4，维护范围 800 米。首次建造使用 `seed/year/modules={}`；不修改游戏的维护规则，也不自动购买飞机。

提交读回实际 `CONSTRUCTION.depots`，要求直升机运输模式、维护池 4、维护半径 800；缺失时即使 `built=true` 也返回 `verified=false`、`service_verified=false`，不得重试建造。`list_depots` 新增 construction、maintenancePool、maintenanceCatchment；购机沿用 `buy_vehicles`，传入返回的机库实体编号，不能传入机场建筑编号。维护由原生模拟处理，实际维护服务和货运仍需运行验收。

预留占地约 170×170 米为估算，入口位于局部 `(0,-60)`，附加停机位槽 1000 位于 `(-26.8,37.6)`。本接口不自动接路、换装、建线或购机。

验证：61 项直升机场/停机坪/设施/总部/仓库模拟 API 测试通过；徐州 `(60,1030)`、旋转 180° 的实机只读原生预览通过，无建筑碰撞，仅清理已识别树木。记录见 `exports/heliport_interface_20261003/preview.json`。尚未在隔离存档提交新机库，未实机验证购机、维护或完整运输；正式施工前先在可丢弃存档验证，保留原施工基线。新增 MCP 工具需要刷新服务；此次未重启服务或重载存档。


2026-10-03 实机追加：用户授权后载入独立副本 `tf3_xuzhou_heli_test_20261003_0849`。专用接口单次建成徐州直升机场，读回 `CONSTRUCTION 83811 / VEHICLE_DEPOT 83812`，直升机模式、维护池 4、半径 800 均匹配；已成功购买两架 H-21。运营读回显示飞机在徐州停靠时 `maintenanceStation=83812` 且 `maintenanceChange>0`，维护状态回升。证据为 `exports/xuzhou_heli_build_20261003/heliport_test.json`、`initial_vehicles.json`、`second_helicopter.json`、`operation_audit03.json`。这些编号仅供历史追溯。尚未验证完成后存档重载或长期稳定性。

货物中转纠正：原生 GUI 的 `line_util.tl` 使用 `getStation2stationsAndDistancesMap` 判断旅客站间换乘；不能将其缺少货站条目判定为货运不通。货站与停机坪须覆盖同一中转仓的库存实体，使用 `getStationCatchables(station,true)` 核对，并最终用仓库装卸日志与城市交付计数验收。徐州原方案缺少两端中转仓，已在施工副本补建两座单模块500库容仓库；不能仅靠两站相邻宣称货物可换装。

2026-10-03 完整货运验收：两架 H-21、两辆 GMC 通用货车分别运行农场集货、空运、城区配送三条线路。两端货站和停机坪均覆盖对应的500容量仓库，实际发生货车卸入仓库、直升机取货及卸入目的仓、配送货车取货和城市建筑消费。暂停验收时城市建筑装卸日志合计卸入42单位蔬菜、消费35单位、库存7，26栋建筑有收货或消费记录；四辆载具均 noPath=false，无问题线路。`getCargoTypeDeliveredPerYear` 此时仍为0，不能单独用它否定供给，应联合建筑库存、itemsUnloaded 和 getCargoConsumedPerYear 验收。农场最大年产68、当时城市年需求119，已形成有效供给但不等于全城满供。原生 app.saveGame 保存完成档 `tf3_xuzhou_heli_supply_complete_20261003`，磁盘文件60620369字节，最终速度0，未重载验收完成档。记录见 exports/xuzhou_heli_build_20261003/final_audit02.json、operation_audit10.json、execution_record.json。

## 建造预览声誉字段（2026-10-03）

现有建造参数、返回字段和一次提交令牌不变，在原生预览的 `check.reputation` 增加声誉统计（部分道路工具直接返回预览对象，此时为 `reputation`）。覆盖总部、仓库、停机坪、直升机场、设施复制，以及使用公共预览函数的建筑入口。

- `available=true`：复用原生 `town_util.getProposalStats / calculateProposalImpact / addTownAuthorityPenalties`，与建造界面采用相同的全新扣分累计口径；`unit=percentage_points`。`total_penalty` 为各城市扣分总和，`total_delta` 为其负值；不是任何单个城市的当前声誉或实际扣分，也不对跨城合计做100上限截断。
- `towns` 按城市编号排序，含 `town/name/penalty/delta/reasons`。原因键为 `Trees`、`Rocks`、`TerrainModification`、`DemolishedTownBuilding`，数值均已乘100，保留小数，不受界面四舍五入影响。
- `scope=immediate_construction_preview`、`actual_score_change=false`：不包含后续运营噪声、污染、恢复等，也不按城市已有扣分历史预测最终分数。
- `available=false` 加 `reason`：缺少原生模块、关键字段不可读取、临界错误、仅结构检查、道路/拆除简化提案等；不返回假零值，不改变原有碰撞/施工放行逻辑。调用者必须先检查 available。

简化的新建建筑提案从原生 `getConstructionResult` 重建仅供统计的 Proposal，保留子建筑模型、位置和业主，并与原生几何预览数量核对。这个统计提案从不提交。道路、拆除和设施改造仍保留既有安全边界，不能为了获取声誉额外执行不安全的 replacement 预览。

实机只读验证：徐州候选直升机场 `(600,850)` 预览声誉损失 `0.14630447946659` 个百分点，来源为地形修改，未施工，未改变游戏速度。证据 `exports/reputation_20261003/preview.json`。129项声誉契约及设施/总部/仓库/直升机/e2e回归通过。隔离加载磁盘脚本已验证。随后通过常驻桥接直接调用仍未返回 reputation（见 live_dispatch.json），因此当前已加载实例尚未启用新字段；需重新加载桥接脚本/存档后才可由常规工具读取。MCP工具描述更新需服务刷新。本次未自动重载或中断当前游戏。
