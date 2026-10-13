# 新通道操作验收清单（已验证范围与剩余边界）

## 2026-10-10 v32 迁移有限实机验收完成

新增具名读取、组件分页、整体快照、路由缓存已通过；两站线路重排及完整恢复、车辆停运标记两步批次/重启防重放、两轮只读运营采样/去重已通过。新自动接取适配器只做dry-run，因原生任务条件不合适没有接取；新增批次购买/出售和非空waypoint等复杂组合仅离线覆盖。本轮不把所有参数组合标为实机通过。

独立备份与固定检查点均写入并验证，未读档；原2222.sav不变，资金/贷款/仿真时间不变，保持暂停。桌面新通道配置原样启动新MCP进程通过，旧桌面连接仍需重连；不需要重载游戏。持续监控和自动接取关闭。证据 `output/live-validation-20261010/resume43/independent_audit.json`，详细范围见 [迁移说明](reference/HEADLESS_MIGRATION.md)。

## 2026-10-10 v32 实现阶段待验清单（历史）

具名工具路由、组件/冻结快照分页、2～32 站编辑、车辆批次、自动接取适配与只读监控已完成实现和离线回归（1522 项测试及 4 项子测试）。v32 已安装，新增部分全部保留“实机待验”，不沿用旧通道通过结果。原有 v31 及之前的有限实机证据不变；铁路同人下车仍按用户要求跳过。

下一次加载后先确认 v32 会话、地图及现有对象，再验证只读能力与快照，最后在授权、预算和备份范围内验证新写接口；监控/自动接取不自动启动。范围详见 [HEADLESS_MIGRATION.md](reference/HEADLESS_MIGRATION.md)，安装证据位于 `output/live-validation-20261010/resume43/deploy/`。

## 2026-10-10 自动保存接入：v31 实机写入验收通过

无面板 `kind=save / save_game` 已实机完成独立测试存档新建、明确覆盖同一测试槽、稳定文件及 SHA-256 校验；默认同名覆盖在发布前被拒绝，MCP 重启后原已验证结果可读取。两次保存各单次提交，最终保存计数2/256、无 pending。详见 [新通道保存说明](reference/HEADLESS_SAVE.md)。输入框、Send 和状态提示均已移除。

`2222.sav` 大小、修改时间及哈希均未变化。前后地图、7台载具、6条线路一致；gameTime5484400、速度0、现金20,023,528、贷款48,870,134不变。测试槽为 `tf3_headless_save_acceptance_20261010_v31`，最终文件33,125,170字节。本次只证明实际文件写入，未重载测试文件（reloadVerified=false）。v30可调用对象类型误拒已由v31修正并实机确认；完整离线1482项及4项子测试通过。证据 `output/live-validation-20261010/resume42/RESULT.md` 及 `fix31/independent_audit.json`。铁路逐人下车仍按用户要求跳过，旧监控未恢复。

## 2026-10-10 用户暂时跳过铁路同人下车：当前验收清单收尾

用户明确要求暂时跳过铁路同一乘客下车。该项状态为 deferred_by_user（未通过、未作废），保留 resume41 的空载观察证据，后续不自动继续运行或追加支出。巴士逐人下车、目的建筑抵达及其余当前有限场景验收已完成；本轮清单没有其他待执行项。

覆盖边界仍保留：原生缓存长期回收、长期持续运行/无限建造和长期盈利未证明；固定翼部分为空载试飞，所有车型、桥隧、编组、货品及机遇参数组合未穷举。它们不是本轮清单全部通过的隐含保证。旧文件通道依此前用户指示暂不纳入。此次仅更新记录，未连接或修改游戏。

## 2026-10-10 铁路追加观察结束：暂停，仍缺真实同人下车样本

用户批准追加 160 模拟秒 / 190 万净支出。本轮实际 147.2 秒、净支出 1,505,238，21 组列车在车身份采样均为 0，前后两站候车均为 0；列车再次完成往返且未出现寻路错误，不能据空载运行判逐人下车通过。目的建筑抵达此前已通过，当前仍余铁路同人下车 1 项。

最终 gameTime5695600、速度0、现金18,300,406、本金47,948,056；偿还本金922,078、利息83,636，其余499,524为净支出。设施报价和换车基金17,415,099保留，无新借款或资本支出。会话、地图及线车身份保持，账本209/256，无pending，进度未保存。下一步应先查真实客流需求，不自动延长运行或改线；无需代码重载。证据 `output/live-validation-20261010/resume41/RESULT.md`、`independent_audit.json`。下文“预算待批准”为历史状态。

## 2026-10-10 目的建筑抵达通过；仅余铁路逐人下车

原巴士乘客中4人已从同人下车移动转为原目的建筑内状态，目标实体经完整 TOWN_BUILDING 分页确认为 Dulverton 建筑。4条闭环证据通过，另6人未声明抵达。TEE已重新出库，短测列车与两站仍无乘客，铁路不能按空载计通过。

本轮64秒、净支出217,884；与前轮合计743.2秒/5,732,893，处于批准750秒/650万内。已暂停，现金19,805,644、本金48,870,134，无新增贷款。追加铁路观察预算（160秒/190万，不借款）待批准；无需代码重载。详见 `output/live-validation-20261010/resume40/RESULT.md`、`partial_acceptance.json`、`RAIL_PLAN.md`。

## 2026-10-10 同一批 10 名巴士乘客实际下车通过

用户批准 750 模拟秒/650 万现金净支出上限及必要运行偿债储备重分配。4 倍推进、近终点 1 倍观察，原 10 人从双在车组件转换为仍存在的 SIM_ENTITY_MOVING，原目的地不变；终点停靠及另一批 10 人上车有独立证据。原生去程713.2秒，终点再发车5483200，补齐巴士逐人实际下车。

实际679.2模拟秒、净支出5,515,009，低于批准上限。两贷各还6期：本金3,623,376、利息310,908；其余1,580,725为净支出，非毛运行成本。最后现金20,023,528、本金48,870,134，gameTime5484400、速度0重复确认，账本203/256、无pending；地图/线车身份保持，无新借款或资本支出。

最终目的建筑抵达未验，巴士结果不替代铁路专用逐人下车；长期无限保证仍无证明。本轮进度尚未保存，要保留可保存2222，无需重载。详见 `output/live-validation-20261010/resume39/RESULT.md`、`independent_audit.json`。以下旧“巴士下车待验”为历史进度。

## 2026-10-10 v29 货物身份实机验收通过

新会话已加载 v29。船 48556 的鱼身份分页 7＋7＋1，15 个 ID 与数量、品质总数及上一轮独立名单一致；逐件原生货物/在车组件核实。旧已卸货 29856 未混入，空船返回 0，巴士原 10 人身份与默认货物人数查询回归通过。v28 乘客和 v29 货物的错误空列表修复现在均已现场通过。

30 次请求全部完成，无 pending，账本 200/256；地图/线车保持，游戏暂停，时间 4805200、现金 25,538,537、本金 52,493,510 未变。没有新代码或世界修改，无需再次保存或重载。证据 `output/live-validation-20261010/resume38/RESULT.md`、`live_acceptance.json`。

同一乘客实际下车/最终抵达仍未验收，保留储备后余 649,154，未擅自延长运行或新增贷款。长期缓存回收、无限运行/建造及长期盈利仍非已证明结论。以下旧“v29 待重载”仅为历史进度。

## 2026-10-10 v29：货船身份读取修正已安装，待重载

继续暂停补验时发现非乘客分支也有空列表问题：船 48556 实际 15 单位鱼，原生数量/品质一致，但 v28 身份为 0。完整分页 3116 个货物后，逐件原生组件独立确认 30066–30080 在船上；旧货物 29856 虽有运输历史，当前已不在船，不能把历史记录当当前载货。

v29 使用有界完整实体遍历，按 SIM_CARGO.cargoType 和当前在车组件匹配，避开不支持的 SIM_CARGO 专用枚举。专项 65 项、全套 1457 项及 4 子测试（53.11 秒）、源码/安装版六 Lua 编译和安装字节核对通过。已部署 generation `d71340f0bf1a491a86200d47b2261d07`，仍需重载 2222 并进入地图才能实机验收 7/7/1 分页；不能提前宣称 v29 现场通过。

全程暂停、现金 25,538,537/本金 52,493,510 未变，无 pending，账本 200/256。无地图修改，无需新保存。乘客 v28 通过仍有效；同一乘客下车、长期无限保证仍待验，未扩大融资或恢复监控。见 `output/live-validation-20261010/resume37/RESULT.md`、`live_audit.json`、`validation.json`。

## 2026-10-10 v28 乘客身份分页实机验收通过

已确认 v28 新会话，暂停读取巴士乘客分页 4＋4＋2，10 个不同 ID 与原生人数、品质总数及上轮独立名单一致；逐人双在车组件均指向同一巴士、线路和上下车站。空列车返回 0 与空列表，默认人数查询响应保持。此前“在车 10 人但汇总 ID 空列表”的乘客读取问题已现场验证修正。

8 城/14 产业、6 线/7 车及运行状态保持。22 次请求完成，无 pending，账本 200/256；游戏时间、暂停、现金 25,538,537 和本金 52,493,510 不变。2222 文件 SHA 较上轮变化，原因未确定，不能把运行状态一致表述为存档字节未变；新 SHA、文件属性见报告。本轮未保存或重载，无产品修改，无需再次重载。证据 `output/live-validation-20261010/resume36/RESULT.md`、`live_acceptance.json`。

同一乘客实际下车/最终抵达仍未验收，非乘客身份枚举分支本轮未实测；长期无限保证仍不成立。储备外余 649,154，不足覆盖约 48 模拟秒内两笔合计 655,714 的下一期贷款及运行费用，故保持暂停，未新增贷款。以下旧“待重载”段为历史记录。

## 2026-10-10 v27 实机身份读取通过；v28 乘客枚举修正待重载

新会话 v27 已确认；用户 2222 保存/重载保留上轮返库、巴士往返和偿债成果。巴士人数/品质总数均 10，但汇总 ID 映射为 0，未误报下车。完整分页 1271 人并释放快照后，独立核实 10 名乘客的两种在车组件都指向同一巴士、线路和上下车站；另验证实际步行/建筑内组件。整个过程保持暂停，现金 25,538,537、本金 52,493,510 不变，账本 200/256 无 pending。

v28 用已实测的 SIM_PERSON 与双在车组件核对取代乘客汇总映射猜测，保留有界扫描/分页及冲突失败。专项 63 项、全套 1451 项及 4 子测试、六 Lua 编译与安装 SHA/字节通过，已安装，尚未加载。请重载 2222、进入地图并保持暂停；本轮没有世界修改，无需再次保存。后续先校验乘客分页，逐乘客下车和长期无限保证仍未通过。详见 `output/live-validation-20261010/resume35/RESULT.md`、`identity_acceptance.json`。


## 2026-10-10 v27：乘客身份只读接口已安装，待保存重载实测

`get_vehicle_cargo` 新增显式开启的有界在车实体 ID 分页；`get_sim_entity` 读取同一实体的在车/候车/步行/建筑内组件，缺失或删除不误报送达。原生 CargoTypeId 和数组索引分开，默认旧人数查询不增加身份枚举；施工 256 上限保持。专项 58 项、最终全套 1446 项及 4 子测试、六 Lua 编译及安装字节/SHA 核对通过。

当前游戏仍 v26、暂停，现金 25,538,537、本金 52,493,510，储备外 649,154；本轮无模拟、施工、借款或自动重载。v27 generation `d640e0d4b7a84c7993d306844dcf1425` 已安装但未加载。请先保存当前现场到 2222（保留上轮返库/往返/偿债），再重载、点击开始进入地图并保持暂停。后续先做暂停状态身份读取，长时间运行尚无新增预算。逐乘客下车和长期缓存不能提前标通过。证据 `output/live-validation-20261010/resume34/RESULT.md`、`validation.json`。


## 2026-10-10 收尾：巴士往返与结算证据已补齐

最新逐项矩阵及独立核验见 `output/live-validation-20261010/resume33/RESULT.md`、`independent_audit.json`。巴士完成 Rugeley→Dulverton→Rugeley，原生两段 762.8/676.4 秒，起点再次发车时间 4758200；到站前后车辆账户净增 303,900 支持客运结算判断，不等于逐乘客身份匹配。新一批乘客 10 人中原生低品质标记 1 人，服务质量不算验收通过。四台已完成测试的载具已回库，用户两艘船保持。

最终已独立确认暂停：1963-04-16，现金 25,538,537、本金 52,493,510，8 城 14 产业身份保持，账本 200/256，无 pending。储备后余 649,154，不再延长模拟。安装版与 v26 部署 SHA 一致，源代码仅相差预期通道注入值；无产品改动、重载、GUI、监控恢复或 Git 提交。本轮运行进度尚未再次保存。

不能宣称所有项目无条件全过：有容量列车已有实际载客和往返证据，但逐乘客最终下车仍未独立验证；原生缓存回收、无限持续运行/建造、长期盈利也未验证。已有功能与有限场景测试不因这些边界作废，也不为补长期保证无期限消耗测试资金。历史节中的旧“待加载”状态由最新矩阵定位。


## 2026-10-10 最新：v26 剩余有限验收补充结果

后续最新证据汇总在 [HEADLESS_TRANSPORT_20261009.md](HEADLESS_TRANSPORT_20261009.md) 和 `output/live-validation-20261010/resume32/RESULT.md`；以下各节均保留当时状态，不能把旧“待加载/待验”文字当成当前结论。

铁路实际载客 1 人、原生客运机遇单次接取并完成、500 次连续查询及归档后 MCP 重启读取已分别取得实机证据。原油跨方式交付后炼油生产及维护恢复、机场/铁路步行连接、0/1/2/4 倍速与暂停的后续验收见 resume30/31。新客运测试巴士实际载客 10 人；本轮新增车库、两对停靠点、线路及一辆巴士合计报价 1,373,287，无新增贷款。最终暂停，用户已保存“2222”，文件更新/稳定/SHA 和独立备份完成，未重载最终存档。

通过范围为记录中的场景与有限窗口。原生缓存回收、无限持续运行和无限建造未验证；审计文件增长且 256 条施工防重放限制仍保留。新巴士完整往返、逐乘客下车和长期盈利未单独证明，不以原生任务 Complete 替代这些结论。无需为本轮结果部署或重载代码。

## 2026-10-10 最新：v20原油跨方式交付及当前资金预算

见`output/live-validation-20261010/resume23/RESULT.md`：新车库/道路/配送站、两条线和两台载具完成独立验收，原油2单位经直升机→独立坪→仓库→货车到炼油厂，货物实体对账；配方需4，消费仍待下一批。工业库存与品质样本口径差异不等于空仓/坏货。用户已暂停并保存2222，备份/SHA稳定核实，无需本轮代码重载。

用户选择普通资金、先制定融资预算。`resume23/financing/PLAN.md`为仅方案：Large42,000,000、清旧Small3,333,336，后续资本上限27,000,000；六个月压力后余4,637,230。机场布局源和当前报价尚缺，融资未执行。六组仍有条件/长期待验子项，不能标全部通过。未自动改速/保存/重载、未使用GUI/旧文件通道、未恢复监控、未Git提交。

## 2026-10-10 最新：货车站四向通路及航空共库通过；车库配置修复 v20 待保存重载

v19重载后地图/430米道路保持且暂停。货车站原生明细在入口高程与临时道路节点完全相同时返回critical“无法建造”、无碰撞。现场核对后仅调整入口高出路面0.10米（既有0.25米保护内），原生两阶段预览通过并单次建造46847；节点46861与入口边46864、外部路46862/46863的四个方向TRUCK原生通路各单请求通过。该对照支持临时节点重合假设，不是引擎根因证明，也不能将高出0.10米当作通用规则。

直升机场46555（购机库46583）、独立坪46542、500容量仓库46548单次建造并读回。机场/坪原生道路自动链接存在；三货运设施含货车站均覆盖库存46549，容量只计500，航空catchables不包含炼油厂。静态共库通过，实际装卸、中转、工厂消费尚未开始。

四座新设施报价2,341,196，含此前道路合计2,432,152，在380万资本上限内。末读现金13,407,304、贷款27,880,954、速度0；现金较本轮初始减少96,498，扣款归属未确定，完整报价储备仍保留，不当作免费施工。旧报价、全部新报价及三个月债务/运营/换车储备后余1,573,651，为预算假设，非收益保证。

接入车库时，已有相邻路口配置触发“no writable member userModifiedLaneConnections”，预览前停止，未建车库；后续延路命令未发送。v20删除对原生只读userModifiedLaneConnections/userModifiedTrafficLightStates的赋值，保留读取拒绝自定义配置的保护以及实际车道、横道、信号配置复制/映射。增加原生只读setter模拟回归；专项99项、全套1356项+4子测试通过（50.74秒），源码/安装版六Lua编译、独立字节及SHA通过。已安装，实机修复效果待加载。

持久账本87/256，无未决。原六组仍有未完成子项，未购车/借款/改速/运行新链，无自动保存/重载、GUI、旧文件通道、监控恢复或Git提交。新设施尚未确认保存，必须先保存2222，再重载v20并保持暂停；不要重放已完成的四座设施和旧道路。下轮重新解析道路，完成车库、工厂配送端和车辆线路，再验收实货。

证据：`output/live-validation-20261010/resume22/RESULT.md`、`construction_ledger.json`、`live_acceptance.json`、`08_station_paths_result.json`、`15_inventory_depot_survey_result.json`、`16_depot_road_preview_result.json`、`17_final_read_result.json`、`offline_validation.json`。

## 2026-10-10 最新：v18 原生接路预览拒绝；v19 补全错误明细

v18重载确认地图、430米道路、两线两车保持且暂停。显式高程1.800003米的货车站frontage在首个原生预览阶段收到“Native construction geometry unavailable”，没有提交；不能推断高差已解决。v18丢弃原生check明细，当前根因未知。独立读回设施仍5座、道路保留、账本75/256且无未决。

v19只增加有界、UTF-8完整的失败阶段/原生明细/入口参数诊断，不放宽检查、不追加查询或自动重试。全套1353项+4子测试通过（51.50秒），源码/安装六Lua运行时编译、字节及SHA通过；已安装，需重载2222保持暂停才能获得具体拒绝原因。本轮无世界修改，无需重复保存；原六组仍有未完成项，不能称建站失败已修复。

无自动保存/重载/改速、GUI、旧通道、监控恢复、Git提交。证据：`output/live-validation-20261010/resume21/RESULT.md`、`live_acceptance.json`、`03_station_preview_result.json`、`04_reconcile_result.json`、`offline_validation.json`。

## 2026-10-10 最新：v17 重载道路保留；入口高程参数 v18 待加载

已确认v17新会话、8城12产业与地图指纹保持，430米道路4节点/3边逐项与施工后记录一致。2222已更新并独立备份（SHA256 46fd45852f6cc9d76c77397f2fe48e1e080423a829e9074853e6b1235035e422）。游戏暂停，两辆既有车仍分配；现金13,503,802、贷款27,880,954，持久账本74/256，无未决。

货车站frontage预览在提交前被原生入口高差保护拒绝，未重发、未施工。独立地形读回：西侧站中心2.50米，道路接口1.800003米，东侧备选中心1.300003米；仅换到道路另一侧仍不满足0.25米接口高差约束。placeConstruction强制取中心地面高程，缺少基础对齐参数。

v18为道路/电车车库及公路车站的frontage预览增加可选z，基础相对中心地面调整限2米，其他设施/缺frontage拒绝。默认放置行为保持；原生0.25米入口高差、唯一端口、碰撞、道路配置及提交前重验均保留。此2米是适配器的保守上限，不是原生任意地形保证。尚未做v18原生验收。

专项90项、全套1347项及4子测试通过（51.08秒）；六Lua运行时源码/安装编译、独立字节与SHA通过。已原子安装v18，当前游戏仍v17，需重载2222保持暂停。本轮没有世界修改，无需为本轮重复保存；无自动保存/重载/改速、GUI、旧通道、监控恢复或Git提交。原六组仍有待验子项。

证据：`output/live-validation-20261010/resume20/RESULT.md`、`live_acceptance.json`、`03_station_preview_result.json`、`04_height_diagnosis_result.json`、`offline_validation.json`、`full_tests.log`。

## 2026-10-10 最新：v16 电车/列车路径读取通过；v17 车站接路待加载

原生 MOVE_PATH 的 edgeId/dir 已在电车8边、列车45边上独立确认；库存质量口径仍待实际提货对照。新430米测试道路单次建造并读回，报价90,956留储备；尚未确认保存。当前暂停，现金13,503,802、贷款本金27,880,954；未新建设施/购车/借款。

货车站单独贴路预览碰撞，未提交。v17把既有受限 frontage_node 联合接路适配扩展至车站，保留道路配置及碰撞保护。专项75项、全套1332项+4子测试通过（50.91秒），源码/安装版编译及独立字节/SHA通过；已安装，尚待实机加载验收。用户需先保存2222中的新路，再重载并保持暂停，不能直接丢弃未保存道路。

剩余六组仍有子项；无自动保存/重载/改速、GUI、旧文件通道、监控恢复、Git提交。详见 `output/live-validation-20261010/resume19/RESULT.md`、`live_acceptance.json`、`transfer_plan.json`。

## 2026-10-10 最新：v15几何/库存实测通过；路径类型差异修正v16待加载

用户重载2222后，8城12产业、两站两车两线与资金保持；两车初始在库，铁路/电车保存重载持久性已验。两座铁路站PERSON几何各219边读取通过，但对外链接均为空，旅客接入/交付仍未通过。油平台400原油与质量样本0并存，最早实体有效、pickupTime=-1；只证明该样本未提货，不将质量0解释为空仓/坏货，也不外推全部货龄。

单次派出已有电车并保持暂停以生成MOVE_PATH，v15端口助手返回数字，与随游戏API声明的PortId对象不符，触发Lua类型错误。已停批、独立核对，未重发；无未决，账本58/256。v16增加官方edgeId/dir记录支持，并对数字等非对象端口保留有界诊断、明确不支持解析，不猜编码、不调用图查询。修复尚未实机验证，路径组仍待验。

专项44项、全套1328项+4子测试通过（50.96秒），源码/安装版六Lua编译和独立字节/SHA通过。v16已原子安装，须用户重载已保存2222保持暂停；无需保存此次临时派车，重载恢复已验证的在库基线。其余六组仍有子项，无改速/自动保存重载/GUI/旧文件通道/新增建设购车借款/监控恢复/Git提交。证据：`output/live-validation-20261010/resume18/RESULT.md`、`live_acceptance.json`、`station_access_evidence.json`、`offline_validation.json`。

## 2026-10-10 最新：剩余六组继续诊断；v15待加载

当前8城12产业与两辆在库车辆保持，游戏暂停。两座铁路站未观察到城市道路自动链接；采油平台仍有400原油但质量样本0，未知口径不计为空仓/坏货。唯一送粮机遇无现成服务线路、失败罚款2400万，未接受。当前无旧图机场/仓库等设施可复用，不能沿用旧实体。

v15补充显式开启的只读路径端口解码、铁路/航空站PERSON几何图和逐槽库存最早货物样本，均有数量上限、不寻路、不施工，原生异常不吞掉。专项105项、全套1320项+4子测试通过（48.45秒）；源码/安装版六Lua编译及独立字节/SHA通过。已安装，实机仍待重载；原第2/3/4/6/7/8组没有因此自动关闭。

用户已保存2222，新增铁路/电车成果独立备份并校验；本轮无自动保存/重载/改速、GUI、旧文件通道、新增建设/购车/借款或Git提交。证据：`output/live-validation-20261010/resume17/RESULT.md`、`live_acceptance.json`、`offline_validation.json`、`fix/deploy/deployment.json`。

## 2026-10-10 最新：v14电车和新铁路实际往返、返库通过

v14已加载，自由道路末端双侧停靠点实建通过；16座DUEWAG电车实际出库、西→东→西往返并回库。两座160米客运铁路站、铁路车库和约411.04米新轨道实建/读回，8个端口有向通路各自单请求通过；原生7节142座TEE编组实际出库、北→南→北完整往返、回库，均有独立状态和车库库存证据。铁路样本载客0、车站城市步行接入未验，不能称真实旅客交付通过。

原剩余8组已关闭第1与第5组，其余6组有待验子项。末读8城12产业保持、电车/列车均在库、speedup=0、持久账本57/256且无未决。用户手动运行和恢复暂停，代理未改速。铁路资本报价17,835,538，最终现金13,503,802、贷款本金27,880,954、合计月供520,297；设施扣款不明报价储备6,240,608仍保留。

本轮无代码修改/部署，不需为了加载新代码而重载；新增成果尚未验证保存重载。无自动保存/重载、GUI、旧文件通道、监控或Git提交。证据：`output/live-validation-20261010/resume16/RESULT.md`、`tram_acceptance.json`、`rail_acceptance.json`、`live_acceptance.json`、`54_final_read_result.json`。

## 2026-10-10 最新：电车库四向原生通路通过；自由道路末端停靠点修复v14待实测

v13已加载，在2222测试图完成200米双向电气化道路和电车库44614/45805单次施工及独立读回；新路口43175连接左右道路46138/43954和入口46210。每个请求仅一个有向原生寻路，四向均通过。尚未买电车、建线或实际出入库，不能计为电车运营通过。客运铁路站cargo=False的原生预览通过，尚未建造。地图原8城10产业保持，新增渔场43997；总部替换/移动为45426，已重新调查并确认当前PERSON双向图，不能声称旧总部未变。

停靠点预览在生成原生提案前因自由道路末端缺少BASE_NODE_CONFIG被拒绝，没有提交或重试。v14仅允许经实时核对的未冻结、度数1且唯一连接目标道路的自由端省略不存在的配置；已有配置（含空配置）保持并重映射，缺配置的路口仍拒绝。边编辑预览摘要新增端点位置、相邻道路和冻结状态，改变后提交前拒绝。专项130项、全套1305项+4子测试通过（49.87秒）；六Lua运行时、16局部变量编译余量、安装字节及SHA独立核对通过。v14已原子安装，运行游戏仍v13。

本轮新借款500万，已观察一期月供214583，最新现金4785417/本金4791667。道路+车库报价1387311继续保留扣款储备，设施扣款时点未明；未购车辆报价452772另留。当前已由用户暂停；用户允许测试时临时1倍速结束暂停，但新通道尚未接入改速，代理未改速。须先保存当前道路、车库和贷款状态到2222，再重新加载以启用v14；不得重放贷款和施工。原8组仍仅第5组整体完成，其他7组仍有子项。未自动保存/重载，无GUI/旧文件通道/监控/Git提交。

证据：`output/live-validation-20261010/resume15/RESULT.md`、`live_acceptance.json`、`15_tram_paths_result.json`、`16_stop_preview_result.json`、`17_stop_guard_diagnosis_result.json`、`tram_budget.json`、`fix/deploy/deployment.json`。

## 2026-10-10 最新：总部完整重载验收通过；v13电车/客运铁路适配待加载

v12在2222新测试图完成总部独立布局、保存重载、真实子网络/链接有界读取和全部4个PERSON端点到城市道路双向图验收。8城10产业身份保持，现金/贷款0，0线0车，持久账本8/256、无未决。完整总部64KB读取问题已有实机替代验证；不证明长期模拟安全。

v13合并两个剩余接口缺口：电车库frontage_node贴接仅接受双向电气化电车道路，并保留/重映射道路配置；铁路站可选cargo=False创建原生旅客站台、楼梯和时代站房，默认货运保持。专项132项、60种原生模板核心模块对比、全套1297项+4子测试通过（48.66秒）；源码/安装版六Lua编译及独立SHA通过。原生新设施/实车验证待重载2222，当前运行仍v12。

本轮游戏全部只读，用户保存的总部已确认保留，无需再次为本轮保存。原8组仅第5组整体关闭，其他7组仍有子项。证据：`output/live-validation-20261010/resume14/RESULT.md`、`hq_access_acceptance.json`、`live_acceptance.json`、`native_passenger_comparison.json`、`fix/deploy/deployment.json`。


## 2026-10-10 最新：普通资金借还款通过，总部已建；v12待保存重载

新普通资金测试图2222已由用户手动保存并保留独立备份。v11当前会话完成1900万借款、独立到账、全额还款及独立清零；现金0、贷款0。总部原生PERSON入口预览双向通过后单次建造42253，独立主楼/位置/归属与真实道路链接读回通过；完整建后有向图仍待验收。

完整总部get_entity响应67,671字节超过64KB，批次停止且未重放；有界布局读回与无未决账本独立确认。v12新增get_facility_access(entity,person_graph=true)，只返回有界总部PERSON网络与真实链接参数，纳入未连接子网络；不生成提案或查询原生路径。专项25项、全套1229项+4子测试通过（48.60秒），源码/安装版6种Lua编译及独立SHA通过。代码已安装但当前会话仍v11；需要用户先保存新总部再重载2222，避免成果丢失。

原8组仅第5组整体关闭，剩余7组中普通借还款等子项进一步完成。未自动保存/重载/改速，无GUI、旧文件通道、运营监控或Git提交。证据：`output/live-validation-20261010/resume13/RESULT.md`、`live_acceptance.json`、`fix/deploy/deployment.json`。


## 2026-10-10 最新：勘探成功、机场/独立坪飞行通过；v11待新加载

本轮关闭原第5组勘探成功分支：新农场59088/建筑83085，原8城32产业保持；原生通知中的74565实际是道路节点，不能当产业ID。新机场54755按先道路、后原生贴路建成，4条自动道路链接读回通过；外接城市公路仍未验。DC3完成两端实际落地与停靠索引1→0→1，S64在独立停机坪实际落地、返航；均为空载试飞，不代表客货交付。测试机/线已独立验收后清理，恢复原7线11载具。

v11新增只读总部PERSON连接图预览、可选逐库存槽质量读取，收紧地形mode校验。全套 **1219测试+4子测试通过（48.88秒）**；源码/安装版六运行时编译、原子安装及独立SHA通过，游戏仍v10。普通资金借贷、总部、电车外接/新轨道运行、有容量编组、仓库下游、路径/库存口径、长期稳定等原剩余7组仍未闭环。

末次账本250/256、pending为空；重载不会重置持久化施工限制，未清记录或放开上限。下一步需用户保存当前成果，再加载关闭无限资金的新沙盒测试图；确认v11和地图指纹后继续，不复用旧ID。无自动保存/重载/改速、GUI、旧通道、寻路压力测试、监控或Git提交。

证据：`output/live-validation-20261010/resume12/RESULT.md`、`live_acceptance.json`、`final_comparison.json`、`fix/deploy/deployment.json`。

## 2026-10-10 最新：v10共库读取、边坡持久性与直升机实际交付通过

用户确认手动删除线路6及两辆货车，本轮按7线11载具基线继续。v10已加载；仓库59748实际容量1000、库存81462，直升机场71974/站68459/组71181共库原生读回通过；铁路48086与货站58704共同库存57350。独立停机坪79036未覆盖库存，未误报共库。196边坡顶点保存重载后保持，最大误差0.00000447米。

临时S-64直升机54965实际在采油平台装10单位原油，飞行并卸入仓库：机上10→0、真实库存81462从0→10、坏货0，交付质量约0.900。年度交付字段仍0，不能替代物理库存证据。直升机回库双重读回后出售，空临时线51128删除，恢复7线11载具。原8城32产业身份/位置/资源保持；速度1、账本219/256、pending为空。仓库保留10单位测试原油，未清货。

本轮没有代码修改/部署，不需要重载。新工人机遇98408未核实客运到岗，未接受；无限资金普通借贷仍不适用。剩余8组见本轮live_acceptance.json，包括新电车接入/新轨道实际通行、机场/总部、有容量编组、仓库下游消费、勘探成功、条件金融/机遇、路径与质量口径、长期稳定性。全操作仍未全部通过。

证据：`output/live-validation-20261010/resume11/RESULT.md`、`inventory_acceptance.json`、`helicopter_delivery_acceptance.json`、`slope_persistence.json`、`final_comparison.json`、`live_acceptance.json`。无自动保存/重载/改速、GUI、旧文件通道、监控恢复或Git提交。

## 2026-10-10 最新：铁路双向查询、固定编组运行回库、边坡过渡通过；v10待加载

v9已加载。站口52682的76082↔82596两方向TRAIN查询各一次通过；旧轨道/停机坪/站组/核心地形重载后保留。固定二节EMD编组75486在临时线83240实际出库移动、停靠索引1→0、回库后独立确认并出售，临时线已删除；容量0，不证明载货服务或完整往返。

新4×4米核心至7.9米、8米过渡带，11原生步骤全部完成，独立196顶点误差最大0.00000447米。未自动保存，持久性待用户保存重载后核实。初始新增炼油厂76603与旧消失68310分别登记；本轮初末8城32产业不变，原8线13载具保持，速度1，账本209/256且pending为空。

v10新增只读get_facility_inventory：原生仓库/车站对应真实库存ID与去重容量，缺失库存明确unknown，未声称交付。专项16项、全套**1202测试+4子测试通过（49.95秒）**；六运行时编译和独立安装SHA通过。已安装待用户保存当前地图并重载，随后核实仓库扩容/共库。车辆原生路径tuple解析、实际全链交付、条件贷款/机遇和长期验证仍有缺口。没有改速、GUI、自动保存/重载、监控恢复或Git提交。

证据：`output/live-validation-20261010/resume10/RESULT.md`、`live_acceptance.json`、`slope_independent_comparison.json`、`final_comparison.json`、`fix/deploy/deployment.json`。

## 2026-10-10 最新：接轨实建、地形、独立停机坪通过部分验收；地图变化已停批

v8已加载，旧双向停靠点重载保留。铁路站口直接100米轨道82596，独立读回端点和空配置移除；曲线候选因曲率过大拒绝，未提交。列车通行未验。4×4米地形调整到8.3米，一次原生提交及独立100点/核心网格读回通过，未测边坡分块。

160米道路先建并读回，独立停机坪79036按原生吸附点+7米路半宽建成，7条实际道路连接去重3条。未验证飞行、共库和吞吐。收尾原炼油厂68310从产业清单消失，32→31，原因未知，后续施工已停；8城和原8线13车保持，identity_delta.json留证。现场速度4→1，本轮没有改速请求。

v9补充铁路/电车单请求单方向通路查询，正确区分原生forwardOnly=false与缺失标志。**1186测试+4子测试通过，48.41秒**，六运行时编译和独立安装哈希通过。已安装待用户保存当前地图并重载；下轮先重新调查及对账炼油厂变化，再核新设施持久性和通路，不能重放旧请求。全操作仍未通过。

证据：`output/live-validation-20261010/resume9/RESULT.md`、`live_acceptance.json`、`identity_delta.json`、`fix/deploy/deployment.json`。

## 2026-10-10 最新：双向停靠点与勘探结果读回通过；v8待加载

v7已实际加载。停靠点单次提交后旧边81981替换为82913，站点82907/82912、站组82922已独立读回；相邻节点公交双向通路分两个原生请求通过。尚未验收实际客流和本轮新站重载持久性。

已登记黏土勘探最终failed，操作结果与独立原生历史通知2701一致、pending为空；未发现资源不等于通道失败，没有重发。初末8城32产业及原8线13载具身份不变，速度1，写入账本187/256无未决操作。

v8为新建铁路设施默认空配置外端增加显式、受限的同提案连接选项，默认仍拒绝，不适用于电车/道路端口；任何自定义信号、道岔、过街配置受保护。**1162测试+4子测试通过，48.22秒**，源/安装六运行时编译及独立SHA通过。已安装但未加载，更未完成原生接轨验收。用户需保存当前测试地图并重载；新轮先核身份、端口和新预览，不重放旧施工/勘探。

详细证据：`output/live-validation-20261010/resume8/RESULT.md`、`live_acceptance.json`、`fix/deploy/deployment.json`。全操作、设施连接和实际交付、适用贷款/机遇、地形实写、长期运营仍有缺口；没有自动保存/重载/改速、GUI、监控或Git操作。

## 2026-10-10 最新：城市需求、站台、产业和电车库实测通过；v7待加载

v6会话 `63.567:table: 000000815028AD50`。旧城市需求pending已严格对账解除；城市29332需求7→6→7完成提交及独立读取。临时线82712终端0→3→0，货品6、50%限载、30秒等待完整保留；已删除测试线，原8线13载具保持。

工具厂83413/产业75698、电车库81274/depot82864已实际建成并独立读回；外部连接和运营未验。原31产业均在，仅增加本轮工具厂为32；上轮仓库模块、铁路货站与道路/轨道重载持久性读回通过。黏土勘探操作 `63.567:table: 000000815028AD50:prospection:1` 已登记，末读仍pending，不能称完成/重发。地形候选因模型/坡度拒绝，未提交；无限资金普通贷款、未服务鱼机遇均未执行。

停靠点快照故障定位为原生不提供文档字段userModifiedLaneConnections。v7明确记录not_exposed，保留其余原生车道/信号/步行道严格检查及未来标志实际值；不是把缺失值视作false。完整 **1143测试+4子测试通过，53.14秒**；源/安装六运行时编译和独立SHA读回通过。已安装generation `de73f4490adf4c2ebf05048edb724a81`，待用户保存当前测试地图并重载后新预览实测。全操作仍未完成，没有自动保存/改速/重载/GUI/监控/Git操作。

证据与下一步：`output/live-validation-20261010/resume7/RESULT.md`、`live_acceptance.json`、`fix/deploy/deployment.json`。不得重放旧请求或已登记勘探。

## 2026-10-10 最新：原生施工取得进展，v6 修复待重载

v5 已实际加载，旧网络pending严格对账解除；8城31产业整轮身份一致。曲线道路、铁路、电气化电车道升级、独立电车道、仓库与扩容、仓库克隆/安全拆除、铁路货站、固定MU购入/在库读回/出售均有原生提交及独立读回。保留仓库59748和货站74620等测试对象；未把几何建成当成运输或持久性验收。

停靠点及站台预览暴露原生快照转换缺口；城市需求提交因正常模拟版本第三项变化在原生派发前拒绝。需求保持原值，当前pending为 `5e6bf603e8af48349b206b67383d6357`，后续写入已停。v6修复NodeId转换和城市身份比较，增加严格、单次、证据驱动的拒绝恢复；停靠点具体缺字段仍待新版诊断，不标记修复完成。

**1132测试+4子测试通过**，43.58秒；诊断断言补测40通过；源/安装六运行时编译及16局部变量余量通过。v6已原子部署并独立校验SHA256，generation `dbb14086772e485080dd32696b536a3a`。需要用户保存当前测试地图并重载以加载新版。下轮先读身份/pending，在任何town_cargo工作流读取前处理确证旧拒绝，独立核对后仅用新预览。不得重放施工或旧令牌。

全操作、实际最终交付、新设施连接/MU运营、普通贷款/合格机遇、长期维护及重载持久性仍未全部验收。没有自动保存/重载/改速、GUI、监控恢复、Git提交或推送。

详细证据与下轮顺序：`output/live-validation-20261010/resume6/RESULT.md`、`live_acceptance.json`、`fix/deploy/deployment.json`。

## 2026-10-09 最新：v4 重载确认，v5 新增产业对账修复待加载

当前实机会话 `4152.706:table: 00000081FF170710` 已确认 v4。11 个只读请求正常；原 29 产业未移除/移动/替换，新增畜牧场 44614，8 城和 8 线/13 载具身份保持。旧 pending 62c88afedd5a4b5d9e92b6c794f51966 未解除，测试区仍为空，本轮没有施工或重发。

精确名单恢复条件会拒绝新增产业。v5 保持默认精确匹配，另提供安装器显式 opt-in，仅允许全部原对象不变时登记产业增量；新增明细落入对账回执与持久账本。仍拒绝对象移除、移动、替换、重复 ID 与未知结果，保留原始错误、源码哈希、令牌和会话验证，旧预览不可复用。本次基线保留原 29 产业，不改写历史名单。

专项 54 通过；全套 **1114 passed + 4 subtests**，42.05 秒；源/安装文件各六运行时编译及局部变量余量通过。v5 已原子安装，generation `5c2b6163900f48568579f4324202cc30`，待用户保存当前测试存档并重载后实机对账和继续施工。不能标记剩余操作全部验收。

证据：`output/live-validation-20261009/consolidated/resume5/RESULT.md`、`identity_delta.json`、`live_acceptance.json` 和 `addition_fix/deploy/deployment.json`。


## CURRENT: recovery/signature checks passed; native enumeration fix awaits reload

v3 native recovery of request601232a6f8b440e49cc5d66fca7b24d3 succeeded, then independent
pending read was clear. A NEW curve passed native preview and signature comparison.
Its commit62c88afedd5a4b5d9e92b6c794f51966 stopped before applyProposal at unsupported
forEachEntityWithComponent(BASE_EDGE). Independent site readback remains empty.

Replaced enumeration with the deduplicated node-segment index; this supported index read
passed natively (1763 edges/1703 nodes; not full component-detail acceptance). Broad mocks
now enforce native unsupported-iteration restrictions. Durable network phase journaling
precedes command dispatch; post-dispatch/unknown outcomes cannot be reconciled as unsubmitted.
The one legacy error is pinned to its archived receipt and exact reviewed source hash/line,
old session, consumed token, player and map. No generic reset/replay.

Final identity check failed: farm75886 at(356,-4856) disappeared, cause unknown; industries
30→29, other towns/industries unchanged. Difference recorded, old references invalidated;
new survey required. Migration uses the final observed29-industry snapshot, not a waived assertion.

**1105 passed,4 subtests passed**,43.23s, six-runtime compile preflight passed.
Installed generation `0afb87ba4bd14cd0938fed1608814f15`, SHA256
`308ac72a832df263b59d045593f5fa5c045c02b0d409c0a8ec9a6553b5e284e7` independently matched. User should save the CURRENT test map and reload;
then fresh identity/pending reconciliation and entirely NEW preview are required.
Other native construction/MU/workflow/operational acceptance remains incomplete.
Evidence: `output/live-validation-20261009/consolidated/resume4/RESULT.md`.
No actual new construction, speed change, automatic save/reload, GUI, monitor or Git push.

## Previous: v2 loaded; durable rejection recovery fix installed, awaiting reload

Native v2 loaded in session `1850.463:table: 00000081371BF370`; fresh identity preserved
all8 towns,30 industries,8 lines,13 vehicles. Speed1 retained. No construction performed.
Recovery of old commit `601232a6f8b440e49cc5d66fca7b24d3` failed safely because
MAX_ENGINE_RESPONSES=8 had evicted its error proof; the old durable ledger omitted error.
This live gap was missing from prior recovery tests. Native signature repair is still unverified.

Errors now persist in the durable ledger, surviving cache eviction and reload; conflicting
proof is refused. The original host-archived native rejection was independently recovered.
An optional installer-pinned one-request migration binds that exact pre-dispatch rejection
to the original epoch, consumed token, player and full map. Release default remains nil;
no arbitrary caller proof, global pending reset, mutation replay or automatic recovery.

**1096 passed,4 subtests passed**,42.91s; source/installed compile checks passed across six
Lua runtimes with16 reserved locals. Installed generation `273d193bcc954f00978f29ade3ca2866`,
SHA256 `1ee0c71d2ea2d83e55c8b5f7f3e4004449199df14eafe3b4d559bdb333ea938e` independently verified.
User reload required. Then fresh identity/pending read; reconcile only the exact old request
if still present, independently confirm unlock, and create a NEW preview. Never replay
old construction or recovery request IDs. Other native acceptance stages remain incomplete.
Evidence: `output/live-validation-20261009/consolidated/resume3/RESULT.md`.
No automatic game save/reload, speed change, GUI, monitor, commit or push.

## Previous: extended reads passed; typed network signature fix installed, reload required

Generation b22b7bb3311f4fa0b19af2d288d38a2b loaded successfully in the native game.
300 consecutive extended engine reads passed (900 raw frames matched), durable count125;
68 requests archived, fresh host recovered first/last results with no redispatch.
Finite-window proof only. Large facility pagination, fixed MU inventory, town delivery
statistics and real-stock activity reads passed. No final city delivery is established.

The first curve commit was rejected **before native dispatch**: `Network endpoints or template changed`.
Independent site readback found no new edges/nodes/constructions. Request
`601232a6f8b440e49cc5d66fca7b24d3` remains engine-pending; do not replay or bypass it.
Old generic userdata serialization reproduced the rejection offline when wrapper addresses
changed but lane values did not. The live signature components were not captured.
Typed lane/edge/node snapshots now replace address-bearing fallbacks, reject incomplete
snapshots, and preserve genuine change detection. Narrow persisted-proof reconciliation
was added; native errors/timeouts/partial results cannot be cleared through it.

Full regression **1079 passed, 4 subtests passed**, plus source and installed compile
preflight in six runtimes with16 reserved locals. Installed generation
`b60f42b8c3614528ae589e7a39dd156b`, SHA256 `97ebe01680721d750b6cea26792d02af5f4e735c10c2172c3535cd34bf680286` independently matched.
User reload is needed to activate the revised GUI/engine script. Fresh identity and pending
reconciliation precede any new preview; old tokens/request IDs stay consumed.

Warehouse79726/stock79657 is retained after reload and now holds500 bad fish/500 capacity;
prior80 fresh units are historical. No disposal or line change. Current speed1 retained.
Other new construction/workflow/MU and final-consumption native tests remain incomplete.
Evidence: `output/live-validation-20261009/consolidated/resume2/RESULT.md` and
`live_acceptance.json`; no game save/reload, GUI, monitor, Git commit or push.

## Previous: native load-limit fix installed; receiver still requires reload

User reload exposed native `too many local variables (limit is 200)` at original
line 6622. This was a bridge load failure; no game query or mutation was sent.
Private codec/station/stop helper scopes now release module-level locals. Full
regression **1060 passed, 4 subtests passed**; six Lua runtimes compile source and
installed variant with 16 extra reserved locals. Installer now enforces this check.
Offline compiler margin is not proof of native loader success.

New generation `b22b7bb3311f4fa0b19af2d288d38a2b`, SHA256
`c63ff8e12e43ce30c5b4b3ca79cb5cb91197df023d59163be7ef0aa0b24ccd34` installed and independently verified.
User must reload the failed GUI script before native acceptance can resume. Preserve
remaining tests and fresh-map revalidation; do not replay old requests. No save,
GUI, monitor, commit or push. Evidence: `output/live-validation-20261009/consolidated/load_fix/RESULT.md`.


## Previous: consolidated adapters installed; reload required for native acceptance

Generation `673d22ce7a6d4bbc8d1ba2bf585b3a93` is installed, SHA256
`a222de4034054d28a80c3b15ad1e415811339410619eb1d1778ad7dc4e8f5149`. Independent installed-file hash matched;
previous file backed up. Running GUI Lua still belongs to the prior generation.
No automatic game reload/save was issued. User save/reload is the next runtime gate.

Consolidated capability revision `consolidated-20261009-v1` includes bounded road/track
geometry, road upgrades/stops, fixed multiple units, facility modules/parameters,
compact large-facility receipts and paged layout reads, line terminal selection,
guarded workflow commits and tracked test-object cleanup. **New native writes remain
unverified.** Extended pure-read GUI quota now rolls beyond 256; mutation/preview
budget 256 and unknown-result blocking remain. Full offline suite: **1055 passed,
4 subtests passed**, 43.17 seconds. Later nested-error formatting change passed all
9 targeted identity/diagnostic tests. No commit or push; other edits preserved.

Finite soak on prior generation `347bcd6b467c45378791bd1ba5779221`: 2160.005 seconds
idle on the same slot, 300-query burst, 304 total requests, 312 log frames all matched.
MCP restart recovery passed; 48 run requests archived, 256 hot entries. Independent
local reading recovered the first archived result after stop, without a new request.
**Overall status remains stopped_incomplete:** original industries 77019 and 78872
vanished and new industries 80749/81166 appeared. No other original identity changes.
Do not waive identity assertions or treat this as the same unchanged scene. Old entity
references/previews are invalid; resurvey after reload. Disappearance cause is unknown.
The original generic TaskGroup message is retained; local comparison proves the precise
identity failure. Future runner diagnostics now preserve nested exception causes.

73 same-PID process-memory samples ranged 8865087488–9057468416
private bytes; first 9057468416, final 8912125952.
These include simulation activity and prove neither native cache bounds nor unlimited
runtime/construction. This basic-query soak does not live-test the new extended-read fix.
No game mutations, speed change, GUI, save/reload, monitor, commit or push this round.

Evidence and remaining native checklist:
`output/live-validation-20261009/consolidated/RESULT.md`, `implementation_result.json`,
`remaining_acceptance_plan.json`, and `soak/independent_audit.json`. Preserve the
strict stop-on-error/no-replay policy. The matrix below distinguishes prior native
passes from newly implemented adapters and unresolved operational evidence.

## Previous: targeted cargo reads and two ship-to-warehouse transfers verified

Generation `347bcd6b467c45378791bd1ba5779221`, session
`51535.704:table: 000000AD628FDFB0` confirmed. All13 vehicles and8 lines retained;
ship line stops/config unchanged. No new vehicles, global speed change, game save,
reload, monitoring, Git commit or push. Prior user save copied/hashed before construction.

New native read acceptance: 544 unique STOCK_LIST IDs in six bounded snapshot pages;
actual fish40 onboard, passenger25 onboard, waiting54; empty native isVeryBad flag
correctly reported without falsely marking spoiled cargo. Warehouse counts and quality
counts agree. Production stock quantity and quality counts disagree (crude400 vs0,
fish284 vs0); scope unresolved and explicitly retained as a limitation.

Existing port warehouse55601 was full with500 bad fish. Under sandbox test authorization,
a separate receiver warehouse79726 / real stock79657 was previewed, submitted once and
independently read back at(-490,-5500), capacity500, native build quote905,321.
It is RETAINED; old warehouse/cargo preserved. Module annual maintenance quote25,000.
First receipt40 verified against loaded-then-empty ship and new destination stock.
Second sequence: source loading16 → onboard40 → destination departure → onboard0;
warehouse40 →80, bad0. Thus two real intermediate warehouse receipts are verified.
AnnualDelivered remained0 and was NOT used as transfer evidence. No city final
consumption, outbound delivery or long-term supply stability is claimed.

Harbor construction detail query exceeded encoded65536 limit (202308 bytes); safely
stopped and diagnosed, never replayed. Smaller warehouse readbacks succeeded.
Fixed-wing airport construction, fixed MU, remaining rail/tram infrastructure and
native path tuple extraction remain open. No reload needed for this completed round.
Evidence: `output/live-validation-20261009/headless_cargo_reads/live_acceptance.json`.

## Previous: targeted cargo read adapters installed; live acceptance awaits reload

Official installed API declarations were checked (paths and SHA256 in api_sources.json).
Added get_vehicle_cargo(vehicle,cargo), get_stop_cargo(line,stop_index,cargo), and
get_stock_cargo(stock_list,cargo). All validate current entities/components and cargo
resource IDs before native cargo calls. Stock reads cover at most64 slots. Vehicle
and stock summaries expose countAgreement; empty stock does not imply spoiled cargo
from native isVeryBad alone. Annual shipped/delivered remain annual engine statistics.
Added list_map_entities ids_only=true for small discovery pages, preserving snapshots
and deleted-entry markers. Oversized-result fallback now records explicit failure
reason and encoded byte count, retaining the existing no-replay message.

Regression: 984 passed, 4 subtests passed. Tests include sparse cargo IDs, passenger0,
invalid/missing entity and stock components, invalid stop, empty cargo, native errors,
count disagreement, slot bound, and a >100KB stock record with ID-only recovery.
This is mocked transport validation, not new native cargo read acceptance.
New generation `347bcd6b467c45378791bd1ba5779221` installed with prior-file backup and byte verification.
Game still needs user reload. No world modifications, save, speed changes, monitoring,
Git commit or push. Live survey retained the same map and13 vehicles; no test vehicles
were purchased in this round.

Next: verify fresh generation/session/map, re-resolve vehicles/lines/cargo IDs and stock
entities, sample targeted loads and waiting/stock data; require consecutive observations
at the right stops and destination evidence for delivery. Never treat noPath=false,
stop visits, a load decrease alone or annual-statistic difference as proof of throughput.
Rail/tram infrastructure, fixed-wing airport construction and fixed MU remain open.
Evidence: `output/live-validation-20261009/headless_cargo_reads/`.

## Previous: rail consist and fixed-wing service / return / cleanup passed

Live generation `9e6a969dbd494118bb81890bbe83c3a1`, session
`50457.437:table: 000000AEB5A1F320`. One DB V100 + two tank wagons purchased as a
single consist75387, native part quote6,269,028, independently read back ordered parts
and FUEL-compatible capacity44. Actual movement and departures from both line56361
stops verified. Physical return to rail depot56748 independently verified.
Temporary DC-4 aircraft69431 purchased/assigned via new channel; observed takeoff,
landing and departures from both line70351 stops. Physical return to airport depot67480
verified. Both test vehicles sold once and independently absent; all 13 pre-existing
vehicles and 8 lines retained. Rail and air stop configurations unchanged.
The two airports, original aircraft62752/71173 and line70351 were external additions:
this validates operations using them, not agent construction of fixed-wing airports.
No save/reload/global speed change/monitoring/Git commit/push performed this round.

Actual cargo/passenger delivery remains unproven. A read-only STOCK_LIST page100
triggered the 65,536-byte framing fallback; stopped and reconciled locally, no replay.
Stock payload reduction and targeted delivery readback remain open. Fixed multiple
units, new fixed-wing airport construction and remaining rail/tram infrastructure
coverage are also open. Native path edge tuple extraction remains unavailable.
Evidence: `output/live-validation-20261009/headless_consist/live_acceptance.json`,
`07_preview_result.json` through `31_final_readback_result.json`.

## Previous: native depot-mode fix installed; reload required

Live preview after reload rejected before purchase: native VEHICLE_DEPOT has no
carrier field. Independent readback confirmed TRAIN/ELECTRIC_TRAIN transportModes,
all 11 original vehicles unchanged, rail depot empty, and no unresolved pending request.
The adapter now validates enabled native rail transport modes. Fixtures use the actual
missing-carrier shape; added road-only, disabled-rail, electric-only and changed-depot
cases. Full regression: 963 passed, 4 subtests passed; diff whitespace check passed.
New generation `9e6a969dbd494118bb81890bbe83c3a1` installed with backup and byte verification.
No native purchase, assignment, speed change, save or reload was performed.
Actual consist purchase and cargo delivery are still pending user reload and fresh preview.
Evidence: `output/live-validation-20261009/headless_consist/04_preview_result.json`,
`05_reconcile_result.json`, and `depot_modes_deploy/deployment.json`.

## Previous: rail consist adapter deployed; reload required

The new 2–8 part rail consist preview/commit adapter passed 959 tests and 4 subtests.
Generation `4195a4e051c941738f3ef7cbc86a62c9` is installed but not yet loaded in game.
No consist purchased. Next live test will re-resolve depot/models and preview a
DB V100 with fuel tank wagons for the existing FUEL line. Native quote, compatibility,
actual purchase/loading/delivery/return remain unverified. Fixed multiple units are
excluded. No automatic reload, save, speed change or monitoring.
Evidence: `output/live-validation-20261009/headless_consist/RESULT.md` and `PLAN.json`.

## Previous: four temporary carrier vehicles returned and cleaned

User restored original tram57362; testtram78168 then moved, physically returned to31746,
and was sold with independent absence verified. Original tram remains running.
All four temporary vehicles78168/77755/78064/42362 removed;11 pre-existing vehicles and7
lines remain. Rail locomotive and ship have both-stop evidence; tram has six-stop history.
Helicopter second service stop/delivery, cargo delivery, fixed-wing, full consists and
remaining infrastructure tests are NOT passed. At that checkpoint no reload/deployment/monitoring was pending.
Native path tuple references remain unavailable. Evidence:
`output/live-validation-20261009/headless_ground_diagnosis/TRAM_COMPLETE.md`.

## Latest: physical return to NEW depot passed

Test vehicle 77843 physically left and returned to depot 76602, confirmed by sequential
IN_DEPOT → EN_ROUTE → GOING_TO_DEPOT → IN_DEPOT states and independent depot lists.
Only that vehicle was briefly stopped/resumed; no teleport or global speed change.
Vehicle and temporary line 76068 cleaned up; original 7 lines/12 vehicles retained.
New depot/access road retained; no auto-save. This closes the prior return-destination
gap, not every remaining project test. Evidence:
`output/live-validation-20261009/headless_depot_return/RESULT.md`.


## Latest: actual depot service test passed with return destination limitation

New depot 76602 dispatched a test bus onto a new 126.6m city access road. Temporary
line 75071 reused Park Road/Queens Road; vehicle 77471 recorded departures from both
stops, then physically returned to game-selected EXISTING depot 45146. Return to the
new depot is not certified. Vehicle and empty test line cleaned up and independently
verified; original 7 lines/12 vehicles retained, stop configurations unchanged. Access
road and new depot retained. No auto-save, speed change or reload. Evidence:
`output/live-validation-20261009/headless_depot_service/RESULT.md`.


## Latest: live directed junction acceptance passed

Generation `4457a543fe0e430faa0f7e5042ce567b`: 18 read requests, 12 native path
queries in separate engine requests. BUS/TRUCK passed every directed pair among depot
entrance and left/right road edges, including both through-road directions. Junction
lane/crosswalk references are current. Depot survived user save/reload; prior test vehicle
remains removed. East road changed to 33363/town medium; freshly resolved, cause unknown.
No game mutation or speed change. Actual moving-vehicle service/return still pending.
Evidence: `output/live-validation-20261009/headless_junction_path/RESULT.md`.


## Latest: new depot vehicle purchase accepted; directed paths pending

New depot 76602/construction 47135 passed a single Rampini purchase, independent
in-depot readback, sale and cleanup (vehicle 30292 now absent). 11 requests; no route
assignment or vehicle exit/return claim. Added one-query-per-request directed junction
path reader with fresh lane resolution and configuration readback; 904 tests and 4
subtests pass. Installed generation `4457a543fe0e430faa0f7e5042ce567b` requires
user save/reload. Evidence: `output/live-validation-20261009/headless_frontage_operation/RESULT.md`.


## Latest result: native road-depot frontage built (2026-10-09)

Generation `3af93ba85bf54992b64e4bb3dd227209` completed one native commit and
independent readbacks. Construction 47135/depot 76602 share road node 26113 through
native entrance 74506; both replacement roads retain lane configurations. 13 requests.
No repeat signature rejection, no GUI/save/reload/speed change. Native vehicle paths,
actual entry/exit/operation, endpoint lane-connection readback and reload persistence
remain unverified. Automatic TP_NET_LINK scan is empty for this directly shared-node
connection and must not be interpreted as a route test.
Evidence: `output/live-validation-20261009/headless_frontage_signature/RESULT.md`.


## Latest frontage acceptance (2026-10-09)

The four automatic-removal model groups are confirmed trees/hedges and native preview
passed (cost 1121630). Commit was rejected by the road signature guard before native
dispatch. Independent road/depot readback unchanged. Generic lane serialization may
include opaque wrapper addresses; replaced with explicit native lane fields and mode
flags without weakening change detection. 895 tests and 4 subtests passed. Installed
generation `3af93ba85bf54992b64e4bb3dd227209` awaits user reload and fresh live validation.
Evidence: `output/live-validation-20261009/headless_frontage_trees/RESULT.md`.


## Latest native frontage findings (2026-10-09)

Joint preview reports no collision or critical error. It is blocked solely by four
`autoRemovalEntity2models` groups (66212,14407,21078,21081); live model names remain
unknown. No construction or token. The tree classifier now checks all model names,
rejects mixed/unknown groups, and returns bounded diagnostic names. 49 focused tests
passed. Generation `34aaa6b4c49a48f7915ae0c8dbc07c89` installed, awaiting reload.
Evidence: `output/live-validation-20261009/headless_frontage_diagnostics/RESULT.md`.


## Latest frontage diagnostic status (2026-10-09)

The repaired generation loaded successfully. Eight live requests completed/reconciled;
the joint road-depot preview stopped at the asset-removal guard after entrance binding.
No construction commit or token, and independent local road/depot readback is unchanged.
The exact removal category was not returned by that build, so it is still unknown.
A bounded diagnostic-only change is installed as generation
`c8f6ef6775d44acfadae905ba5446938` and awaits user reload. It returns removal
categories/entity IDs while keeping the preview blocked. 44 focused tests passed.
Evidence: `output/live-validation-20261009/headless_frontage_adapter/RESULT.md`.


用户授权在当前测试地图验证既有各类操作，包括道路、铁路、有轨车道、航空、线路、购车、货品和装载量。原文件通道暂时忽略，监控继续停止。不得把旧通道验收记录或模型目录读取当作新通道写操作通过。

## 当前阶段

### 2026-10-09 贴路车库适配修复：等待重载验收

已加入可选 `preview_depot.frontage_node`，仅支持普通两段道路节点与公路车库。
联合提案绑定当前原生入口，保留并重映射端点车道/过街引用；路况变化、自定义配置、
入口歧义、高差、原生错误、碰撞及其他资产移除均拒绝。未声明接路或运营已通过。
全套离线测试 **889 项及 4 子测试通过**；最终小改后相关 **44 项复测通过**。
修复版 generation `e94cd60a5bb14c25915a51b6f16839ac` 已备份部署，需用户重载才能进入原生验收。
本轮未发游戏请求、未施工、未保存或改速。证据：`output/live-validation-20261009/headless_frontage_adapter/RESULT.md`。

### 2026-10-09 新建造接口重载验收：贴路绑定缺口

generation `e2dd2255ffba4f6f9ec9271866e3fb9a` 已实际加载。
13 次只读/预览请求正常返回；公路车库两个候选均被原生道路碰撞拦截，没有发放
施工令牌，没有任何施工提交。最终车库实体清单不变、速度仍为 4。
证据 `output/live-validation-20261009/headless_structure_adapter/acceptance.json`。

已定位代码缺口：新接口沿用 construction-only 提案，没有迁入原直接贴路流程的
道路节点/生成端口联合绑定；`connect=false` 只关闭事后补路，不等于完成吸附。
旧 expectedEntrance=20.26 注释也不能替代后续原生 35 米端口证据。
应补接经过审查的节点绑定、道路配置保留和独立连通读回后再试，不加大退距、不忽略
碰撞、不重放旧脚本。本批施工及其他车库/站点类型仍未通过实机验收。

### 2026-10-09 重载后扩展接口实机通过

`headless_extended_adapter/acceptance.json`：76 次请求、262 个原生日志分帧逐项一致。
新读取接口均正常返回；城市分页跨 MCP 进程/引擎事件续读及释放通过。
此前测试公交和线路重载保留已确认。装载比例、货品选择、强制卸货及等待时间完成
预览、单次提交、独立读回；乘客配置恢复后与原 LINE 完全一致。独立货运测试选择
肉类 7、厚木板 13，比例 25%，目的站禁装并强卸；没有把配置成功称为实际交付。

电车、水运、直升机、柴油机车各单台购入，逐台在库独立读回后出售；没有配线运营，
未验证固定翼飞机或完整列车编组。旧测试公交及两条专用测试线清理通过；最终保留
原有 7 线/12 载具，速度保持 4。没有自动保存或重载；清理结果的保存持久化待验。
全部原城市和产业仍在，新增一座农场已单独记录。详见该目录 RESULT.md。

下一批补接车库（ROAD/TRAM/RAIL/WATER）、公路客货站、铁路货站的有界预览/提交。
复用原建造处理器，预览默认关闭额外接路，提交前重新预览、单次使用令牌和未知结果
阻断；读回施工实体不等于道路/铁路接驳或运营通过。接口离线验证后才部署，需重载实测。

该批现已部署：generation `e2dd2255ffba4f6f9ec9271866e3fb9a`，完整离线回归
877 项测试、4 项子测试通过（新增 32 项结构接口测试）。证据目录
`output/live-validation-20261009/headless_structure_adapter/`，状态为等待用户保存/重载，
尚未实机施工验收。没有提交或推送 Git。

### 2026-10-09 全量验证请求：扩展接口已安装，待重新加载

全套离线回归结果：`845 passed, 4 subtests passed`（33.40 秒），命令为
`PYTHONPATH=server/src;scripts python -m pytest server/tests scripts/tests -q`。
这是模拟原生 API 和本地工具的回归，不是所有游戏功能实机通过。

按需通道新增：货品目录；单站装载货品、maxLoad 比例、强制卸货及额外等待的
预览/单次提交；无配车线路删除；独立确认在库的单车出售；地形、设施/产业资源、
勘探、贷款、机遇、城市需求及地图分页读取。修改线路时拒绝复杂 waypoint/备用终端，
当前仅支持 2–8 个简单停靠点；货品最多 8 种，等待 0–600 秒。不会静默丢弃复杂配置。
复制有序向量保留 cargoId+1 索引；预览不提交，令牌绑定会话、60 秒及原配置，消费后不重用。
延迟/丢失/失败回调保持防重放保护。删除和出售核验玩家归属及当前配车/在库状态。

新增测试发现并修复地形请求遗漏 terrainEpoch 和地图快照跨引擎实例丢失；快照按
会话存入脚本状态，读取字段仍为现场值，不是整个世界的一致性快照。

本轮没有向游戏提交查询或修改，仅检查本地 receiver 状态（ready、pending=null）后安装。
安装 generation `99d16b64dd374d6e9cb7d41e692bdd97`，SHA256
`1bc015b4fcc8b487cfb5385787a979b592de9452ded8ba63dfcff6a207739566`。
证据：`output/live-validation-20261009/headless_extended_adapter/`。需用户保存并重载后重新
解析会话及地图；不复用旧预览，不自动保存/重载，不提交或推送 Git。

前两批实机已通过：线路创建及重载保留；单辆公交购买、独立读回、配线、停运/恢复、
回库及实际入库。分别见 `headless_line_adapter/RESULT.md` 与
`headless_vehicle_adapter/RESULT.md`。公交仍在库，未以此证明载客运营；车辆重载保留待验。
最新扩展接口尚未实机验证，铁路、电车、其他载具、设施升级、完整接驳及运营等仍待完成。

2026-10-09 14:35 机场前方道路测试：重新读取地图、机场配置及九点地形，备份后原生预览、单次提交建成 80 米平行道路，报价 15259，边 69504/66910、共享节点 63000；两段独立读回核对道路模板、坐标及端点一致。机场 71974 的自动道路连接仍为空，接路验收未通过，城市路网、车辆通行和共库也未验收。原生资源显示可连接车道 local y=-52，新道路 local y=-70，中心线相隔 18 米；自动连接距离阈值未知，不能据此断定根因，不继续盲目补路。8 次请求的 19 个 stdout 分帧与 MCP 响应完全一致。固定槽 tf3_fullmap_auto_map_316631ef91297a85 于 14:34:45 更新，39638762 字节且稳定；施工前备份 tf3_ui_frontage_pre_20261009_1422 保留，未改速、未重载。证据：`output/live-validation-20261009/ui_air_phase1/frontage_live/RESULT.json`。

2026-10-09 机场连接查询重载后实机验收：重新核对八城坐标与 20 座设施，测试机场 71974 位于 (-775,-1100,0.65)，原生自动道路连接为空；同类型既有机场 56472 返回 9 条 TP_NET_LINK，关联道路 29396，按道路 ID 去重为 1 条。新接口正反例均正常返回，5 次请求的所有 stdout 分帧与 MCP 结果独立对比一致，证据 `output/live-validation-20261009/ui_air_phase1/access_live/RESULT.json`。车库 47929 自动连接为空不能推断车库断路，因为该查询不检查直接道路节点连接。机场 71974 接路仍未通过，不把接口通过当作工程通过；车辆路径、共库、吞吐及运营仍未验证。本轮只读，没有施工、改速、保存或触发重载，无需为本轮再次加载脚本。

2026-10-09 14:05 重载后碰撞拦截实机通过：道路端点 65185 重新读回位置 (-690,-1100,1.2)，随后全新只读预览仍报告站点 68459 碰撞、placementBlocked=true、ok=false、几何 buildable=true，但没有再发放 preview_token。没有提交道路，没有修改地图或速度。两次请求的三个 stdout 分帧逐项与 MCP 响应一致，证据 `output/live-validation-20261009/ui_air_phase1/guard_resume/RESULT.json`。此前机场与仓库均在重载后设施清单中保留，不等于运营已验收。

机场接路仍待验证。新增有界只读 `get_facility_access(entity)`，读取实际自动连接及关联道路端点，按真实 link/edge ID 去重，明确不证明车辆路径或共库；无连接返回未观察到道路自动连接，失效实体、原生读取错误、扫描/结果超限返回未知错误而非假成功。面板→新引擎事件→日志测试及相关回归共 45 项通过，原生 API 在离线测试中为模拟实现。代码已安装，需重新加载后实测；不使用旧文件通道，不运行批量寻路，不重放旧施工请求。

2026-10-09 13:47 航空设施实机阶段：当前八城地图重新读取后，直升机场原生预览、单次提交和独立配置读回通过，机场 71974、维护机库 71800、站点 68459，位置 (-775,-1100,0.65)、朝向 90 度、报价 1215334。机场接入道路尚未建造：建成后新预览报告站点 68459 碰撞（placementBlocked=true、ok=false），但几何 buildable=true，暴露道路适配器误发可提交令牌问题；未提交这段道路。已同时修正预览发令牌和提交前复核，明确核对原生 ok、placementBlocked、collisions 及 commitSupported，44 项相关回归通过（含六类拒绝状态及提交前状态恶化不触发原生修改）。修正版已原子安装，待用户重新加载后实机验证；不回放旧令牌。

14 次请求的 32 个 stdout 分帧与 MCP 响应独立对比一致；原生碰撞文案本身含替换字符，仍待修复，不能声称全部字符串编码正确。机场配置 frozen_nodes/frozen_edges 为空，不能据此认定没有原生入口；接路仍需有界端口调查。固定槽 tf3_fullmap_auto_map_316631ef91297a85 于 13:47:09 更新，39374592 字节并稳定，未重载；施工前备份 tf3_ui_air_pre_20261009_1337 保留。证据：output/live-validation-20261009/ui_air_phase1/live/RESULT.json。独立停机坪、机场接路、飞行运营与其他写操作仍未验完。

航空设施新通道已补接 `build_helipad` 与 `build_heliport`，复用现有 `commit_facility` 和配置读回。38 项相关回归通过，其中新增两类设施的实际 Lua 面板→事件→处理器→日志测试，逐事件重建模块；覆盖预览不提交、单次建造、独立配置读回、重复事件/令牌拒绝、未知结果阻断以及 Python/Lua 参数拒绝。原生引擎在这些测试中为模拟实现，尚未记为航空设施实机通过。安装后须重新加载游戏脚本才能继续实机测试。

2026-10-09 12:05 修复后实机验收：重新读取八城地图；旧请求通过严格的 `reconcile_road_rejection` 对账为原生提交前拒绝，未重发。全新预览后成功新建 80 米道路（2 段，报价 15345），再从刚读回的末端节点延伸 40 米（1 段，报价 8065）；三段均通过独立 `get_entity` 核对位置、道路模板、节点引用与双向车道。新旧路段共享节点 67586，提交时接头校验通过。9 次请求、20 个日志分帧完整匹配 MCP 结果。证据：`output/live-validation-20261009/ui_operations_phase2/fixed_live/RESULT.json`。固定槽 `tf3_fullmap_auto_map_316631ef91297a85` 于 12:04:45 更新，37899905 字节且写入稳定；未重载。证明直线新建和明确节点延伸通过，不代表道路全场景、车辆通行或长期模拟全部通过。

2026-10-09 实机道路类型、地形调查及 80 米道路原生预览通过，报价 15345、两段、无碰撞。单次提交返回 `Unknown or consumed road preview; do not retry`，在道路原生提交前被拒绝，不能算建造通过。证据在 `output/live-validation-20261009/ui_operations_phase2/resume2/`，提交 ID `05dcb4d2f7d44b0d9524dfc38d518c90`，不重发。

发现道路预览仅存模块局部变量，没有像设施适配器一样写入游戏脚本状态；不同事件的模块实例不共享该变量。已改为按 GUI 会话保存预览并在消费前写回，补充每次引擎事件重建模块、事件开始快照、重复提交与拒绝对账测试。增加 `reconcile_road_rejection(request_id)`，仅允许对账保存证据明确为上述原生提交前拒绝的道路请求；未知原生错误、部分成功和超时仍阻断。修复后仍需重新加载并进行实机验收，不自动回放原请求。

道路提交仍受未知结果阻断保护。预览令牌限当前加载会话、60 秒内且仅使用一次；提交时再次检查端点和原生提案。沿用已有道路处理器的限制：不允许 junction_commit_suspended、不强行忽略碰撞、不把部分成功当作可重试。当前面板仅支持直线、明确端点、无自动吸附；曲线和较长几何参数需要后续有界传输设计。

## 操作覆盖矩阵（2026-10-09 合并验收更新）

以下替代旧矩阵；上文各时点记录保留为历史。实机通过仅限列出的场景，离线模拟通过不替代原生引擎验收。本轮证据在 `output/live-validation-20261009/consolidated/`。

| 类别 | 已有实机证据 | 仍需验收 / 本轮适配状态 |
| --- | --- | --- |
| 线路、车辆和地图读取 | 本轮同一八城地图，8 条线、13 台载具；五运输类型非空读取 | 新增能力清单和分页设施布局需加载合并版本后实测 |
| 公路新建、明确末端延伸 | 80 米新建、40 米延伸及独立节点/道路读回 | 平滑曲线、有轨道路模板、升级和接驳新增有界预览/提交，离线通过，实机待验；不扩展到桥隧/未知路口 |
| 铁路铺轨 | 既有列车线路运营已验 | 新增 STREET/TRACK 模板铺设与端点检查，实机新铺轨及服务连通待验；frozen 节点和空车道配置拒绝 |
| 铁路货站、分类车库、公路站点 | 先前各场景见结构批次证据，不按既有设施运行推定建造通过 | 接口已接通；未有独立实建证据的铁路站、各类车库、路边停靠点继续保留待验 |
| 仓库与水运卸货 | 仓库 79726 / 库存 79657 实建；两次鱼卸货独立证据为 0→40→80 | 城市最终消费、出库配送、长期吞吐及新增仓库重载持久化仍待验；不是全部链条通过 |
| 设施复制、固定翼机场、独立坪、总部 | 直升机场建造及接路正反例已记录；固定翼飞机在用户机场起降已验 | 设施复制/机场施工、独立坪、总部实机待验；大设施分页读取和精简回执已补接，不能把飞机起降当机场建造通过 |
| 设施参数、模块和仓库扩容 | 原生资源与已有配置已读取 | 新增预览包装、一次提交、完整内部读回及精简回执，离线通过，实机待验 |
| 线路增删和货品配置 | 创建、删除测试线；货品、比例、强卸、等待及恢复原配置已实测 | 新增站台选择预览，保留原其他配置并复核原生终端身份；实机待验 |
| 单车与普通列车编组 | 公交、电车、船、直升机、柴油机车、DC4 单车及 3 节机车+货车编组已验相应阶段 | 固定动车组资源、原生朝向和分组本轮接通；需实机购买/读回/回库/清理，不以普通编组替代 |
| 运营与回库清理 | 电车、柴油机车、船、普通编组、DC4 有往返/回库及测试载具出售证据；直升机有首站与物理回库证据 | 直升机完整货运循环、各类最终货物消费及长期维护仍需连续证据 |
| 货物、维护和路径读取 | 544 个唯一库存分页；载货、质量、维护、等待读取及两次卸货已实测 | 源库存 count 与 quality 总量作用域差异未解；原生车辆路径 tuple 解析未解；新增年度消费与城镇半年交付读取待验，年度差不能当瞬时吞吐 |
| 地形、产业、勘探、需求编辑 | 原有文件通道历史证据保留参考 | 新通道预览/提交/操作读回及未知结果阻断已补齐并离线通过；实机待验，需求品类编辑不等于需求数值修改 |
| 贷款与机遇 | 已有读取证据 | 新通道令牌、持久意图、一次接受及独立读回离线通过；普通资金贷款/偿债风险不能由当前无限资金沙盒证明；机遇接受不等于完成 |
| 测试对象拆除 | 测试载具出售/测试空线删除已实机通过 | 新增只允许本会话渠道所建裸边/空仓库的拆除，离线通过待实测；不调用旧 ignoreErrors 拆除。孤立停靠点修复未接入，不能制造未知破损对象来凑覆盖 |
| 长驻、归档及 MCP 重启 | 旧轮次限时证据保留 | 本轮 2160 秒空闲 + 300 基础查询通信证据通过，但两处原产业消失导致整轮 stopped_incomplete；扩展只读请求跨 256 的 GUI 配额缺陷已修复并离线验证，须新版本单独实测。施工 256 条防重放上限保留 |
| 主机规划、缓存、报表及保存持久化 | 离线全套回归持续执行；历史人工保存/重载另有证据 | 主机侧工具不能计为游戏写操作验收；用户重载后必须重新确认会话、原对象、配置及已存测试结果 |

合并版本的实机顺序：加载→会话/能力/原对象对账→扩展只读跨 256 检查→新鲜资源和地形调查→验证备份→道路/轨道→设施与模块→单台/整列车辆与线路终端→原料运输/卸货/城镇交付→测试对象清理→持久化核对。预览与提交保持依赖顺序，发生原生异常或未知结果立即停止后续写操作并独立对账，不重发。

当前不把新写接口标为“全部验证完成”；合并实现的目的为减少反复部署，不缩减实机证据要求。普通资金贷款、无可用机遇、不可勘探城市等不满足原生条件时，应记录具体拒绝/不适用，不能用模拟通过或拒绝结果替代成功实测。
