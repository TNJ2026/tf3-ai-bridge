# 已停用的生产设施双坪集合（历史记录）

2026-10-05 当前规则：城市使用六设施城市集合；陆上生产点使用四设施生产集合（直升机场、仓库、货车站、道路维护设施），不含客车站和公路车库。两者采用各自显示布局及中型乡村公路，优先评估复用，不按服务对象数量固定新建。捕鱼港口集合不变，既有设施不自动拆迁。

新规划使用[四设施生产集合](PRODUCTION_COLLECTION_TEMPLATE.md)。以下参数、命令与验收记录仅供已有工程追溯，不作为新建指令。

实现状态（2026-10-05）：城市默认模板为 `city-displayed-medium-country-v4`，生产默认模板为 `production-displayed-four-facility-v5`，均采用联合提案。四设施模板、角色校验和提案编译已适配，相关42项离线检查通过；新址原生预览、接路与施工读回仍须执行。旧双坪模板与冻结方案只供追溯。

## 历史执行方式：先修路，再放建筑

历史规划模板为 `config/planning_templates/production.json`，版本 `production-road-first-v3-roadside`，设置 `placementMode: road-first`。包含两个独立直升机坪、一个仓库、一个货车站；仓库采用修复后的两个通用模块配置，采用与城市集合相同的两阶段执行方式：

V3 按原生吸附点重新沿路布置：第一坪局部 `(5,32)`、第二坪 `(50,32)`、仓库 `(125,25)`，朝向均为 0°；货站保持 `(110,-55)`、朝向 180°。两个坪的资源吸附点为 `(0,-25)`，仓库为 `(0,-18)`，变换后均落在距小型乡村道路中心线 7 米的路侧目标点。该退距仅适用于当前道路模板，换路型必须重新校验。三者占地使用 V2 现场包围盒，保留双模块仓库和升级留白。

建筑阶段会查找实际已建主路，并按其对应位置的插值高程设置建筑高程；找不到主路则拒绝提交。离线检查吸附点、朝向和道路目标是否一致，建后再次核对路侧高程。几何对齐不等于原生链接或货物覆盖成功，仍须原生预览及三站共库验收。V3 已在另一位置完成两阶段实建验证，详见下文 V3 记录；每个新址仍须重新预览和验收。

1. 原生预览四段主路，备份后单次提交，重新读取实际道路节点和网络。
2. 两个直升机坪、仓库、货车站及一段入口短路联合预览，绑定刚建成的主路节点，通过后单次提交。货站中心仍为局部 `(110,-55)`，短路终点修正为 `(110,-25)`，对应建筑前方 30 米的外部自由端；最终入口仍从当前原生提案重新解析，不能连接内部冻结节点。
3. 读回核对四设施的位置、朝向和模块、道路网络、货车双向进出，以及两个坪和货站是否都覆盖集合仓库。生产集合没有客站和直升机场，不执行城市客运步行换乘检查。

两个坪各向局部北侧预留 25 米，仓库向东 40 米、向北 30 米，货站向东 30 米、向南 40 米。这些是额外规划留白估算，随整个集合旋转；不能视为升级施工通过。成本不参与比较，仍检查地形、覆盖、碰撞、扩建及道路效率。

执行器为 `scripts/road_first_collection.py`。每个集合使用独立账本键和 `road_first_<owner>/` 证据目录，世界修改保持单次提交；部分成功、未知回调或验收失败即停止，不重发。外接工厂或公共道路单独设计和验收，组内静态通过不代表已接通生产设施或已开始运输。

### 使用方法

先通过规划流水线生成包含新模板的方案。旧方案内冻结的模板不会被磁盘新配置自动替换，需要重新生成目标集合及接路方案，不能给已开始施工的方案直接换模板。

以下 PowerShell 示例中填写本次方案路径、执行目录及集合编号；`--current-map-test` 仅用于用户已明确授权的当前地图测试，已确认独立测试存档时改用 `--isolated-test-save`。

```powershell
$planPath = 'exports/本次规划/network_plan.json'
$executionDir = 'exports/本次规划/execution'
$ownerId = 'P本次生产点编号'

# 只预览主路，不建造；实验预览前会保存备份。
server/.venv/Scripts/python.exe scripts/road_first_collection.py preview --stage roads --plan $planPath --output $executionDir --owner $ownerId --current-map-test

# 获得施工授权后，按依赖顺序各执行一次。
server/.venv/Scripts/python.exe scripts/road_first_collection.py build --stage roads --plan $planPath --output $executionDir --owner $ownerId --current-map-test --authorize-build
server/.venv/Scripts/python.exe scripts/road_first_collection.py build --stage facilities --plan $planPath --output $executionDir --owner $ownerId --current-map-test --authorize-build

# 再次读回验收并保存检查点，不重新施工。
server/.venv/Scripts/python.exe scripts/road_first_collection.py verify --stage facilities --plan $planPath --output $executionDir --owner $ownerId --current-map-test
```

也可以在尚未开始施工时，通过全图入口一次执行两个阶段及方案中的外接道路：

```powershell
server/.venv/Scripts/python.exe scripts/construct_planned_map.py --plan $planPath --output $executionDir --owners $ownerId --mode auto --current-map-test --authorize-build
```

手动分阶段与自动入口二选一，不对已提交的阶段重复执行。建筑阶段的预览需要已建主路的真实读回数据，不能在主路建成前直接调用。本修订已通过离线角色分支、阶段拆分、Lua 编译及批量账本隔离测试；双坪生产集合两阶段实建后的首坪覆盖问题已通过扩仓修复并独立读回验证。新版双模块仓库配置已在另一位置按两阶段整组重建并通过静态验收；新址仍需严格预览及验收，不能跳过覆盖检查。

## 2026-10-04 当前镜头实建测试

原点 `(-1683,3054)`、旋转 180°。四段主路先提交并读回，随后四设施及入口短路单次提交成功。两次独立读回均显示：第一个坪未覆盖仓库，第二个坪与货站覆盖通过；仓库容量 500，模块一致、道路网络和货车双向进出通过。完整静态验收失败，账本保留 `needs_reconciliation`，未重发、拆除或继续施工。已保存独立异常现场存档，未接外部公路、开线或购车。证据：`exports/production_road_first_test_20261004/RESULT.json`。

### 覆盖修复与当前模板

用户授权继续修复后，在原仓库增加原生可用槽位 `632502460` 的通用模块（仓库局部 `(-32,24)`），不移动两个坪、货站或道路。配置接口只做结构预检，保存独立备份后一次严格原生提交成功。修复读回确认两个坪与货站均覆盖仓库，容量由 500 增至 1000，模块及双向货车路径通过，完整静态验收通过。默认模板 `production-road-first-v2` 已纳入两个通用模块；道路先建顺序不变。原始失败结果不覆盖，新增证据为 `exports/production_road_first_test_20261004/repair_verification.json`、`repair_result.json` 和 `repaired_expected_spec.json`。已保存修复完工存档；未验证线路运营或重载。

### V2 新址复建验证

2026-10-04 在 `(-1300,2576)`、旋转 270° 使用默认 V2 模板再建一套：四段主路先建，双坪、双模块仓库、货站和入口短路后建，共两次提交，未追加扩仓或补修。模块一致、两坪和货站的仓库覆盖、道路网络及货车双向进出全部通过，仓库容量 1000。已确认固定完工存档更新并恢复原 4 倍速度，未接外部公路、开线、购车或重载。证据：`exports/production_v2_replay_20261004/RESULT.json`。

### V3 沿路布局实建验证

2026-10-04 在 `(-872,2134)`、旋转 0° 新建一套 V3：四段主路先建，四设施与入口短路后建，共两次提交，无补修。双坪及仓库的实际高程与主路插值高程一致，独立读回发现两个坪各有 4 条原生道路自动链接，仓库有 3 条；这不是车辆端口数量。两个坪和货站均覆盖同一个库存实体，容量 1000，模块和货车双向路径通过。已保存完工检查点并恢复 4 倍速度；未接外部公路、开线、购车或重载。证据：`exports/production_v3_test_20261004/RESULT.json`、`native_road_links.json`。

## 选址与运输规则

大运量航空货运优先利用两个坪分别创建分流线路，对接城市机场两个降落平台，明确各线运量及运力，避免重复计算共享库存。详见[双平台分流规则](GROUPED_CONSTRUCTION_WORKFLOW.md#大运量航空货运的双平台分流)。

无限资金模式默认就近用于生产设施旁，不设固定最小或最大距离，不套用城市集合 500 米退距。实际位置由货物覆盖、地形、接路、升级空间和运输效率决定；详见[集合选址规则](GROUPED_CONSTRUCTION_WORKFLOW.md#无限资金模式的默认集合选址)。

旧实现使用仓库内的 `config/planning_templates/production.json`；历史捕获登记 `exports/hub_template_production_default.json` 仅作为来源记录。此为旧实现记录，不再适用于新规划。

2026-10-04 用户纠正：原集合包含两个直升机坪，初次只提取最近一个属于遗漏。当前默认组合为：**两个直升机坪、一个仓库、一个货运站及组内道路**，不含直升机场和客车站。矿坑集合已补建第二个坪，两个坪和货站共同覆盖同一仓库；默认捕获与模板已切换到 `capture_v2.json`、`template_v2/hub_template.json`，旧文件仅留作历史证据。以下单坪测试描述为此前阶段记录，以本段双坪修正为准。

## 历史捕获及实测记录

以下单坪布局、联合施工入口和验证结果属于旧版本，当前默认模板与使用方法以上文为准。

源布局在 `exports/hub_template_production/template/hub_template.json`，示意图为同目录 `layout.svg`。保留全部原生参数与扩展，使用直升机坪作为局部坐标锚点；包含三段配套道路。货站自带入口由原生生成，不重复复制。已读取确认源直升机坪和货站都能覆盖同一仓库。这是源场地库存覆盖证据，不是车辆线路、吞吐或新位置验收。

用于生产端时，先检查能否直接覆盖生产设施并取到目标货品。需要公路集货时，规划生产设施到货站的车辆路线，保证货站有实际道路通路，货站和直升机坪共同覆盖同一仓库。仓库无需额外接路，也不会自动从覆盖范围之外的工厂收货。货品种类、仓库模块及容量须按生产链核对；外接道路和升级空间按目标位置重新设计。

可复用入口：

```powershell
# 读取当前镜头附近的生产端组合，不施工。
server/.venv/Scripts/python.exe scripts/capture_hub_template.py --profile production --output <新的捕获文件.json>
server/.venv/Scripts/python.exe scripts/fullmap_hub_template.py --capture <捕获文件.json> --output <模板目录>
server/.venv/Scripts/python.exe scripts/hub_joint_prototype.py --template <模板目录>/hub_template.json --output <联合预览包目录>
```

联合提案编译器已支持这三个角色，动态入口绑定仅处理货站。生成预览包默认不开启实时调用或提交，目标地形、碰撞、原生入口绑定、仓库覆盖及双向货运路径仍需实测。当前城市集合的实验提交/验收脚本仍包含客车站与直升机场的专用检查，不可直接用于本模板；可配置布局脚本也仍限城市集合，不能将生成 JSON 解释为生产端已实现一键实建。

本次只新增模板与编译支持，没有建造或拆除游戏设施。相关 40 项离线测试通过，生产端三设施联合包生成成功；未做新位置原生预览或施工。

后续实建（2026-10-04）：用户授权在邵阳粘土矿坑附近放置并接路。三设施与组内道路一次提交成功，沿矿坑北侧既有道路末端直线延长 50 米接通；独立检查模块保留、6000 容量仓库共同覆盖、货站至矿坑道路双向 TRUCK 路径均通过。证据在 `exports/clay_production_20261004/completion.json`，固定完工存档 `tf3_joint_auto_86cae9c9c8.sav`。本轮通用化了实验提交/验收脚本的生产端分支及直升机坪无模块检查；上文“不可直接用于本模板”是此前状态。仍无车辆、线路、运输周期或重载验证，不能以静态通过宣称已开始生产运输或长期安全。
