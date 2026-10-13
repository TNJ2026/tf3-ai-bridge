# Non-UI transport investigation

## 2026-10-10 v32 有限实机验收通过

具名读取、组件分页、局部/全图快照和路由缓存通过；测试线两站倒序后恢复完整配置；两步车辆停运标记批次通过且MCP重启不重发；两轮运营采样覆盖8城/707建筑/7车/6线，第二轮无重复事件。自动接取仅dry-run，未接受不具备条件的任务。实际购车/出售批次、非空复杂waypoint和所有站序组合不在本轮实测范围。

独立审计确认原2222.sav未改、现场仍暂停、gameTime5484400、现金20023528、贷款48870134不变，线路和车队恢复原值，无pending。独立备份及固定检查点`tf3_fullmap_auto_map_f2024f890a729d83`稳定文件/哈希通过，未读档。桌面配置已补新通道环境及600秒工具超时，按实际配置启动的新MCP进程已通过；桌面既有连接仍须重连，游戏无需再次重载。监控/自动接取未启动。详见 [迁移范围](reference/HEADLESS_MIGRATION.md) 和 `output/live-validation-20261010/resume43/independent_audit.json`。

## 2026-10-10 v32 实现阶段记录（实机前）

具名工具路由、组件/整体快照分页、复杂线路编辑、持久车辆批次、自动接取适配及只读监控已实现。1522 项离线测试和 4 项子测试通过；源码及安装件各 12 项 Lua 编译检查通过。v32 已备份安装并校验字节和 SHA-256，游戏尚须重载，MCP 进程须加载新 Python 代码；未把离线结果列为原生通过。

详细接口和边界见 [新通道迁移说明](reference/HEADLESS_MIGRATION.md)。本轮没有发送游戏请求、启动监控/自动接取、改速、施工或保存。历史工作流脚本不能因此直接重放。证据 `output/live-validation-20261010/resume43/RESULT.md`。

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


## 2026-10-10 收尾交叉引用：往返补验、暂停与预算边界

最新逐项矩阵及独立核验见 `output/live-validation-20261010/resume33/RESULT.md`、`independent_audit.json`。巴士完成 Rugeley→Dulverton→Rugeley，原生两段 762.8/676.4 秒，起点再次发车时间 4758200；到站前后车辆账户净增 303,900 支持客运结算判断，不等于逐乘客身份匹配。新一批乘客 10 人中原生低品质标记 1 人，服务质量不算验收通过。四台已完成测试的载具已回库，用户两艘船保持。

最终已独立确认暂停：1963-04-16，现金 25,538,537、本金 52,493,510，8 城 14 产业身份保持，账本 200/256，无 pending。储备后余 649,154，不再延长模拟。安装版与 v26 部署 SHA 一致，源代码仅相差预期通道注入值；无产品改动、重载、GUI、监控恢复或 Git 提交。本轮运行进度尚未再次保存。

不能宣称所有项目无条件全过：有容量列车已有实际载客和往返证据，但逐乘客最终下车仍未独立验证；原生缓存回收、无限持续运行/建造、长期盈利也未验证。已有功能与有限场景测试不因这些边界作废，也不为补长期保证无期限消耗测试资金。历史节中的旧“待加载”状态由最新矩阵定位。


## 2026-10-10：铁路真实载客、机遇闭环及有限长驻补充验收通过

v26 同一 session `22501.621:table: 000000801078E630` 中，铁路 46500 首次实际载客 1 人，原生两个人数口径一致；随后人数归零不单独证明下车交付。Rugeley–Dulverton 客运机遇 57466 单次接取并独立确认 Active→Complete（3491600→4064800，573.2 模拟秒）。新巴士 37173 实际载客 10 人，完整巴士往返及逐乘客下车未单独验收。原先列出的铁路真实乘客与合格机遇闭环待验项由这些证据补齐。

暂停窗口内 500 次连续查询及 4 次边界读取通过：504 唯一请求、同一地图/会话/代次，515.043 秒；248 条归档独立匹配，热账本 256，MCP 重启和归档后旧结果读取通过，无 pending。22 个内存样本为 private memory 8.97–9.04 GiB。历史/槽/日志文件实际增长，原生缓存回收仍未证明；不能称无限常驻或无限建造，施工账本 256 上限保留。较早“pending live soak”的归档后读取和有限内存样本空缺已由本轮补充，长期边界仍保留。

用户手动增建的港口、船舶、农场已独立对账并保留。本轮新建公路车库、两对中心停靠点、一条线及一辆巴士，报价 1,373,287，在既有预算内，无新增贷款。铁路延伸候选因道路碰撞/曲率不合格未提交。末现金 30,999,049、本金 55,798,704、速度 0，7 台载具无 noPath/userStopped，施工账本 194/256。补贴 556 万不计运输收入；实际总收入/总费用未完整拆分，长期盈利与收入/费用比例压力仍非实测结论。

用户保存“2222”后已独立核实文件更新、稳定并备份（32,858,260 字节，SHA256 `3cd06849b7e699b00f61bc2635819c7576dbe1fd39dfa5a6b021bceaeaab9631`）；保存后速度仍 0，未重载最终存档。本轮无源码部署、GUI、自动保存/重载、监控恢复或 Git 提交。详见 `output/live-validation-20261010/resume32/RESULT.md`、`live_acceptance.json`、`soak_reconciled/independent_audit.json`、`68_final_independent_result.json`。

## 2026-10-10：v26自动改速和暂停实机通过

用户保存重载后，新会话22501.621:table: 000000801078E630、v26已核对。0→1→2→4→0四次单独提交均获原生回执和独立速度读回，无pending；最后重复确认暂停。新增模拟35秒，现金45150813、贷款62759742，账本157/256。后续测试按用户授权由Agent自行改速与暂停，不再逐次要求人工改速。原油消费4、三类产出2/4/1重载保留。

铁路端站上下客标志、256容量、cargo0装载和实际往返均已核实，实际乘客仍0。两站约455米、覆盖圆附近建筑北4、南12/16；几何统计有重叠，不代表真实客流服务范围。10人路由字段样本不足以推断全城或引擎故障。真实铁路乘客、合格机遇闭环、长期缓存/持续容量仍待验。

本轮无代码部署、施工、购车、新贷款、GUI、自动保存重载、监控恢复或Git提交。当前暂停；短段改速测试未再次保存。证据output/live-validation-20261010/resume31/RESULT.md、live_acceptance.json、saved_baseline.json。


## 2026-10-10：炼油生产与两次维护恢复通过；用户授权自动改速，v26待加载

用户1倍速运行后手动暂停已独立确认。实际模拟372.2秒（含人工响应），7组样本；炼油厂消耗4原油，生成2燃料/4化学品/1化肥，独立货物来源/生成时间与工厂一致。航空→仓库→货车→工厂→生产本场景通过。Bell47维护两次从低于1回升至1；仅有限窗口，长期容量/缓存仍未知。铁路往返、装载配置和步行图已通过，但车内/站内人数7次均0，实际载客未通过。

末现金45456527、贷款63045456、速度0、账本153/256无未决，4辆车均无寻路/停运错误。现金减少3432439，其中本金1811688；其余净变化不能当完整运行费用。保留旧/新报价、剩余资本、换车及6个月零收入压力储备后余15204791（假设）。粮食机遇消失，鱼37仍无供给网络，未接取。

用户新授权允许Agent控制后续所有倍速/暂停，已记录AGENTS.md。v26按需通道set_game_speed支持0/1/2/4，要求expected_speed、原生单次派发、回调实际速度读回；迟回/失联保留未决阻止重发。83专项、全套1427项+4子测试、六Lua编译和安装校验通过，generation173abac454444774a0a8ca54fd8bb55c已安装，实机仍v25。请先保存2222保留运行成果，再重载进入地图保持暂停；自动改速效果待验，不再逐次要求用户改速。

证据output/live-validation-20261010/resume30/RESULT.md、runtime_acceptance.json、live_acceptance.json、budget_after_runtime.json。无自动保存/重载/改速、GUI、施工、购车、新贷款、监控恢复或Git提交。


## 2026-10-10：v25南站步行图实机通过，等待有限运行观察

用户重载后最初停在加载完成页，新心跳未启动，未发送请求。用户进入地图后以新批次核实v25、session21569.059:table: 00000080FF6876A0，8城13产业未变，现金48888966/贷款64857144/速度0保持。南站读回259条原生边，其中241条PERSON边，关联道路节点13953和32001；有向图双向连通通过。此前机场分页及机场/北站步行图已通过。

现有4线4载具无寻路/停运错误；列车及两站乘客0，炼油输入2、输出0、消耗0。已准备最多约6分钟1倍速观察，待用户手动启动；运行和生产验收未完成。证据output/live-validation-20261010/resume30/。本轮无施工、购车、融资、自动改速、保存、重载或Git提交。


## 2026-10-10：v24机场分页与北站/机场步行图实机通过，v25南站扫描计数修正待加载

重载后8城13产业、12设施及南站新路31802保持，153条账本无未决；现金48888966、贷款64857144、速度0。2222已包含南站改造，独立备份及SHA核实。机场配置3模块/10槽位/3兼容模块，两页1487/928字节完整读回，超64KiB问题在该机场通过。北站和机场有向PERSON图分析双向连通；仍非实际客运或长期安全验收。

南站详细图触发旧256边限额，原因是混合机动车边计入PERSON输出上限；只读批次停止，独立基础查询确认连接和账本未改变。v25保留总扫描1024、PERSON输出256、64网络/链接等界限，分别计数，拒绝未知节点；22专项、完整1400项+4子测试通过，源/安装六Lua编译及字节校验通过。已安装generation354f3bba3bb44cbc9a5c29000e6de83d，当前仍v24，需要重载2222保持暂停，无新增世界修改、无需重复保存。

炼油厂仍2原油、Bell47另2，未推进运行；实际铁路旅客、炼油生产、合格机遇、维护恢复/长期缓存待验。现有粮食/鱼机遇无供给网络，未接取。本轮无施工、融资、改速、GUI、自动保存/重载、监控恢复或Git提交。证据output/live-validation-20261010/resume29/RESULT.md、live_acceptance.json、saved_baseline.json、fix/deploy/deployment.json。


## 2026-10-10：融资、机场及铁路接路完成；v24读取修复待保存重载

用户继续批准既定4200万借款、偿还旧Small3333336和1300万资本上限，均单次提交/独立读回。现金48888966、贷款64857144、合计月供655714、速度0。机场47476及先建接路、北站接路完成，自动PERSON连接存在；南站40米路段40703加宽后为31802，四条自动PERSON连接及两端8个CAR/TRUCK有向通路通过，横道保留。报价合计6218750，南站另保留10万储备；设施扣款未完全归属，仍保留报价，不称免费。

用户2222存档/备份已核实，含融资机场北站，但南站升级发生在保存之后，尚未保存。最后账本153/256，无未决。机场完整配置超64KiB及南站图遗漏道路节点均为只读缺口；v24将配置分页、将实际关联的临街道路端点网络纳入审计，同时保留未知实体拒绝。20专项及完整1398项+4子测试通过，六Lua编译和安装字节校验通过；已部署generation46b5a824e103432e909cf9f7c61322e2，实机仍v23。需要用户先保存当前2222再重载、保持暂停。

铁路实际乘客、炼油消费/产出、合格机遇、维护持续恢复等未完成；静态链接和有限通路不代表全链运营或无限安全。本轮无自动保存/重载/改速、GUI、监控恢复、Git提交。详见output/live-validation-20261010/resume28/RESULT.md、execution_ledger.json、live_acceptance.json、fix/deploy/deployment.json。


## 2026-10-10：v23道路修复实机通过，机场改址预览完成，融资待确认

已加载施工前独立备份；8城13产业指纹未变，道路47447消失，节点32067恢复crosswalks=[32068]和空车道配置，旧未决随存档恢复消失，账本119/256。备份源/目标SHA已复核，不手动清pending。

新会话19288.251:table: 00000080FC30A2D0中，103.752米道路重新预览报价22,768，单次提交7479ac3060364052baf60f623876a18c。独立读回两向车道连接和原横道保留；CAR、TRUCK四个有向原生请求均直穿旧路32068→节点32067→新路47447或反向，通过本次受限接路验收。不是所有路口、自定义配置、行人通达或长期模拟安全通过。

原机场接路弯道碰撞40611，旋转候选碰撞40960/40961，均未提交。最终候选机场(150,750,1.5)、朝向0度原生预览通过，报价5,894,752；城市至机场三段未建道路预览通过，加已建段合计250,321，机场+道路报价6,145,073。先路后机场；后续须刷新端口预览、机场吸附及实际通达验收。未将独立预览称为联合连接完成。

剩余测试资本上限13,000,000；现现金10,222,302、贷款26,190,480、速度0。拟借42,000,000、偿还旧Small3,333,336，前80个月合计月供655,714；含旧报价、换车和零收入费用+20%压力储备，6个月余款18,637,230。用户此前仅选择制定融资预算，待明确批准借款及资本上限。融资预览已读回，无借款/还款提交。最后账本131/256，无未决。新道路未保存；没有自动保存/重载/改速、GUI、旧通道、监控恢复、部署代码或Git提交。

机场城市接入、铁路城市接入/真实旅客、炼油产出、条件机遇、长期维护及缓存等仍未完成。证据：output/live-validation-20261010/resume27/RESULT.md、construction_ledger.json、financing/PLAN.md、live_acceptance.json。

## 2026-10-10：v23 已加载，但重载后的 2222 仍含失败道路；已准备独立恢复存档

v23（generation 82ee65d614d0477f9a4039d2e7a38362）已加载，当前 session 为 19062.673:table: 00000081B4F6A330。只读核查发现道路47447与节点47443仍在，原节点32067的BASE_NODE_CONFIG仍缺失，未决请求17abdade978a454bae71e32cb2d451c5仍保留，持久账本121/256。8城13产业指纹未变，现金10,222,302、贷款26,190,480、速度0。此次加载没有恢复施工前状态，不能清除pending或继续提交。

当前2222已更新且包含测试后状态。已将resume25/pre_native_2222.sav以排他创建方式复制为游戏保存目录中的2222_before_road_test.sav，未覆盖2222。恢复文件32,209,595字节，源与目标SHA256均为2f2b0f299c2d1e59526234b6f224823413bbda3588ade2b9d2d6bae97b285995，已独立校验。需用户从加载列表明确选择2222_before_road_test并保持暂停。

恢复后须重新确认会话、地图、道路47447不存在、节点32067恢复空laneConnections及crosswalks=[32068]，并对账持久未决状态；不得手动清账本或重放旧请求。v23原生修复效果尚未验证，融资、机场及剩余验收继续暂缓。本轮仅查询游戏和准备本地恢复文件，没有世界修改、GUI、自动保存/重载/改速、监控恢复或Git提交。

证据：output/live-validation-20261010/resume26/01_restore_check_result.json、recovery_save_prepared.json。

## 2026-10-10 最新：v22道路已建但横道丢失；v23显式保留配置待恢复验证

原生103.752米道路预览通过、报价22,768，单次提交建成47447/47443，但旧节点32067的BASE_NODE_CONFIG及横道32068未保留。独立读回确认，pending=17abdade978a454bae71e32cb2d451c5，账本121/256；已停批，无重发/清pending/融资。现金10,222,302、贷款26,190,480、速度0。此反例推翻v22“原生会自动再生带横道配置”的假设，不能称道路接入通过。

v23在同一提案中显式写入两向车道连接与原有横道，按官方LaneConnection节点视角解析零基车道索引，受限于每向单条CAR/TRUCK车道，电车/多车道/自定义配置拒绝；读回逐项匹配真实新边、索引和横道。41专项、全套1389项+4子测试通过（50.77秒）；六Lua运行时编译及安装字节/SHA核对通过，已安装，原生效果待验。

用户应不保存本次未通过测试，重载未改变的2222并保持暂停，以恢复施工前节点配置，再重新解析并预览。原存档已独立备份并核SHA为2f2b0f299c2d1e59526234b6f224823413bbda3588ade2b9d2d6bae97b285995；不能手动清未决或将失去横道的现场标记成功。详见`output/live-validation-20261010/resume25/RESULT.md`、`recovery_plan.json`、`construction_ledger.json`。其余验收仍未完成，1300万资本预算/融资暂缓；无GUI、旧通道、自动保存重载改速、监控恢复或Git提交。

## 2026-10-10 最新：机场原生预览通过，v22道路末端接入待加载

v21新机场三模块布局与原生createTemplateFn离线逐槽一致；重载后实机两候选预览通过，北侧当前报价5,896,703。融资预算资本上限由2700万降至1300万，尚未借款/还款/施工。现金10,222,302、贷款26,190,480、speedup=0；8城13产业与11设施保持，新增黏土坑47139来源未知、原对象严格不变已对账。

城市接路遇到真实能力边界：中间路口不支持，外部末端32067有默认空车道配置及人行横道。v22新增显式、单提案的受限普通道路末端处理，保留默认关闭，拒绝内部节点/自定义设置/桥隧等；独立读回要求车道生成且原横道仍在，未通过则阻断，不自动修补。原生行为待实机验证，不将配置重建预测当作连通保证。全套1384项+4子测试通过（52.66秒）；六运行时编译、安装字节和SHA通过。已安装，当前仍v21，需重载2222保持暂停；本轮未改世界，无需重复保存。

原机场/铁路城市接入、铁路实际旅客、工厂产出、合格机遇及长期维护/缓存等仍待验。无GUI、旧通道、自动保存/重载/改速、监控恢复或Git提交。证据与修订预算：`output/live-validation-20261010/resume24/RESULT.md`、`live_acceptance.json`、`financing/PLAN.md`。

## 2026-10-10 最新：v20实机接路与原油跨方式交付通过，已恢复暂停

本轮新建车库、80米延路、工厂配送站及两条原油线；Bell47/AMO各一台。已观察油井→直升机→独立坪→共用仓库→货车→炼油厂的2单位实货交付，源/目标货物实体对账。工厂配方需4原油，目前2已入库、2仍在机上；实际消费/产出待验。原生工业库存数与品质样本数可不同；车辆/中转仓样本相符，不能把工业品质样本0当空仓或过期。

用户手动1倍速后恢复暂停，实际模拟380.6秒（含人工响应），末现金10,222,302、贷款26,190,480；未新增贷款。设施扣款未完全对账，保留报价及换车储备后仅144,850，不能复用已消耗的观察预算或追加工程。新工程/车辆已由用户保存2222，独立核实更新/稳定/SHA并复制交付后备份；保持暂停，本轮无代码部署，不需要重载。无GUI、旧文件通道、自动改速/保存/重载、监控恢复或Git提交。原六组尚有2/3/4/6/8子项未完成，不能称全项目通过。详见`output/live-validation-20261010/resume23/RESULT.md`及`live_acceptance.json`。

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


## Road-depot frontage repair awaiting reload

Optional current-node joint binding is implemented for ROAD depots only. It preserves
outer lane/crosswalk references and rejects changed configurations or unsafe native
previews. 889 tests plus 4 subtests passed; 44 focused tests passed after the final adjustment.
Generation `e94cd60a5bb14c25915a51b6f16839ac` is installed but has not been loaded or natively accepted.
No game requests or world changes in this repair turn. Evidence:
`output/live-validation-20261009/headless_frontage_adapter/RESULT.md`.


## Extended live acceptance completed

The extended batch completed **76 requests / 262 independently matched stdout frames**
in session `39558.089:table: 000000AD57976710`, generation
`99d16b64dd374d6e9cb7d41e692bdd97`. Evidence: `headless_extended_adapter/RESULT.md`.
New reads, persistent map pagination, line cargo/load/unload/wait configuration,
single-vehicle sales and empty-line deletion passed. Four additional carriers
(tram, ship, helicopter, diesel locomotive) passed purchase/in-depot readback/sale.
This does not certify route assignment/delivery for those carriers, aircraft,
train consists or all construction operations. Dedicated test objects were cleaned up;
7 original lines and 12 original vehicles remain. No automatic save/reload or speed change.

## Extended adapter batch awaiting live acceptance (2026-10-09)

The full local suite passed: **845 tests and 4 subtests**, 33.40 seconds.
This does not certify all native operations. The installed demand generation is
`99d16b64dd374d6e9cb7d41e692bdd97`; evidence and backup are under
`output/live-validation-20261009/headless_extended_adapter/`.
The user must save/reload to load it; no reload or game mutation was issued.

Adds bounded line-stop cargo/load/unload/wait preview and one-use commit, empty-line
deletion, depot-confirmed single-vehicle sale, cargo catalog and extended planning
reads. Simple lines only (2–8 stops, no waypoints/alternative terminals). Mutation
completion supports delayed callbacks and keeps unresolved outcomes latched.
Terrain engine requests now propagate their GUI epoch. Map entity snapshots persist
across engine module recreation and are invalidated on epoch changes; fields remain live.
These adapters require fresh-session native acceptance before reporting success.
The 256-entry construction ledger and native cache/audit-growth limitations remain.

Earlier demand-mode line creation/reload and single-bus purchase, assignment,
stop/resume and actual depot arrival passed independently. Neither demonstrates
all carrier operations, passenger delivery, or long-term simulation safety.

Status: bounded query/build request transport passed live acceptance on build
40420: nine read-only command types, road and warehouse preview/commit/readback.
Repeated reads of the same path remain
cached. Both earlier marker experiments are disabled.

## Demand-mode residency test (partial live acceptance)

Live follow-up in the same loaded session confirmed three cases without GUI or
reload: a never-created path returned the native missing-file result; creating
that file afterward made it readable; a second post-startup file also loaded.
Evidence: `headless_transport/dynamic_probe/result.json`. The fixed diagnostic
scripts read only their named marker resource and returned an empty slot value;
they are not an exposed arbitrary-eval tool. No engine/world command was sent.

`install_headless_diagnostic.py --on-demand` now installs a demand receiver with
no preallocated files. It polls the current session-specific filename once per
second, stays on that sequence while missing, and advances only after consuming
a valid request. The host creates the file atomically after durable intent.
Missing-file polling is distinguished from syntax/loader failure; unexpected
errors stop the receiver. Old-session payloads cannot be replayed on a new boot.
Idle update delays no longer exhaust slots; a delayed *submitted request* still
expires and is not resubmitted.

The GUI read-only recent-ID caches hold 256 entries; monotonic slot progression
and the host's durable high-water marks prevent slot reuse after archival.
Completed host records beyond 256 are archived individually and remain readable
after MCP restart. Unresolved requests are never evicted. Construction retains
its existing 256-request engine ledger limit and pending-commit latch; this
change does **not** promise unlimited construction calls.

59 relevant tests pass, including simulated two-hour idle without sequence
advance, 301 consecutive read-only requests, archival recovery, and high-water
replay rejection. Native bytecode cache reclamation is still unverified and audit
files accumulate by request count. No idle time limit does not imply bounded
memory/disk under unlimited traffic.

The installed demand generation and read-only soak evidence are under
`output/live-validation-20261009/headless_soak/`. `scripts/headless_soak.py` waits
for a fresh receiver, performs 36 minutes of idle sampling (no game queries),
then resumes queries, runs 300 sequential reads, restarts the MCP process midway,
checks archived result recovery and map identity, and samples process memory.
It never builds, saves, reloads, changes speed, or resubmits an unknown outcome.
It stops on errors or an operator `STOP` file. Its final success state is
`finite_soak_passed`, not an assertion of mathematical infinity. Whole-game
memory changes also include ongoing simulation and cannot all be attributed to
the transport.

2026-10-09 live result: 2160.003 seconds of idle, all 72 samples at slot 3,
followed by successful wake-up and all 300 burst reads. All 304 total requests
returned successfully (median 0.935 s, maximum 1.798 s); a newly started MCP
process recovered the initial response midway. The final map guard stopped the
runner as `stopped_incomplete`: all eight towns matched, but four industries
disappeared and five appeared. The cause of those changes is not established;
this is not a strict-addition update and the guard was not bypassed.

Independent local audit matched all 304 durable responses, including 48 archived
records, with 256 hot records, no pending request, and high-water 304. The first
archived response matched exactly. The post-archive MCP read and final receiver
and memory checks were skipped by the map guard; direct archive inspection does
not claim those calls ran. First/last idle whole-game private memory was
8,864,366,592 / 8,528,945,152 bytes; this does not establish bounded native cache
growth. The runner exited without replay. See `headless_soak/RESULT.md` and
`independent_audit.json`. Finite idle/resume and burst behavior passed, while
overall acceptance remains incomplete and unlimited residency is not proven.

Follow-up after user authorization to continue: a fresh MCP process successfully
read the original archived response through `read_headless_result`. Current
receiver status was ready, same session, no pending request, and nine read-only
command types completed through demand ingress (slots 305–313). All response
frames were independently decoded from native stdout and matched. A separate
post-follow-up process memory sample was recorded; it is not the missing end-of-
burst sample. Evidence: `headless_read_followup/result.json`, `audit.json`, and
`memory_after.json`. The original stopped soak evidence is unchanged. All 419
server tests passed offline in 23.67 seconds.

Reuse audit: demand ingress currently exposes nine GUI reads and fourteen engine
commands (including readback and previews), not the full original command API.
Static direct-function inventory found 76 handlers, 54 not directly exposed;
this count excludes dynamic registrations and host-only tools, and does not
count original commands reached indirectly by adapters as unavailable features.
Original `create_line` / `buy_vehicles` business handlers use asynchronous native
callbacks. The current UI construction adapter immediately searches for a
response after dispatch, so adding their names to the whitelist alone is unsafe.
Async result forwarding, durable duplicate handling and unknown-outcome blocking
must be adapted and tested before live line/vehicle mutations use this ingress.

Line adapter follow-up: `create_line(station_groups,name)` now reuses the original
business handler via `runRequest` with a completion callback. This single direct
mutation supports 2–8 station groups and an 80-byte UTF-8 name; it buys no vehicles.
It reserves durable pending state before dispatch, emits only upon completion,
merges delayed completion into fresh state, and retains the block on failure or
missing line identity. Duplicate events/callbacks do not re-execute or re-emit.
The original engine path documents synchronous callbacks; deferred mocks test
robustness, not proof that native callbacks are delayed. No original business
handler or original-file event path was replaced. Vehicle mutation adapters
remain unexposed.

Seventeen parameterized tests cover synchronous/deferred completion, failed or
identity-less responses, replay after module recreation, concurrent mutation
blocking, fresh-state merge, host/Lua validation, and demand ingress without panel
input. Full server suite: 436 passed in 23.46 seconds; subsequent host/Lua parity
test strengthening: 17 passed. Installed with backup under
`headless_line_adapter/deployment.json`; fresh load and native line creation plus
independent readback are still required. No live line was created by this change.

Subsequent fresh-load native acceptance passed: demand generation
`fa86d8f1bcf746938bf1e6a81fa75520`, session
`36375.89:table: 000000AE66014E50`. One empty line named
`TNJ Headless Line Test 20261009` (entity 75205) was created once, using currently
resolved Park Road / Queens Road groups 56041 / 56081. Independent line-list and
LINE-component readback confirmed exactly one addition (7 to 8), old lines
unchanged, two stops, passenger-only loading with maxLoad 1, and zero vehicles.
All 20 request responses were independently matched to stdout frames. Stable
pre-line save was copied and SHA-256 verified (40,921,401 bytes). No GUI input,
speed change, vehicle purchase or replay. Post-create save/reload persistence,
vehicle routing and service operation remain unverified. Evidence:
`headless_line_adapter/acceptance.json`, `create.json`, and `pre_line.sav`.

Vehicle adapter follow-up (pending fresh-load native acceptance): four bounded
direct operations now reuse the original business handlers and line adapter's
durable completion path. `buy_vehicles` requires count 1 and excludes implicit
line assignment; `assign_vehicles` accepts exactly one vehicle and validates the
current vehicle, line and stop index before native dispatch; `set_vehicle_stopped`
requires an explicit boolean; `send_to_depot` exposes no sell-on-arrival option.
Incomplete purchase/assignment lists or failures retain pending state and preserve
the original partial result in the engine journal. They never authorize retry.

Thirty vehicle tests cover host/Lua argument bounds, stale vehicle/stop rejection,
headless dispatch without panel input, sync/deferred/lost/rejected callbacks,
duplicate events after module recreation and pending mutation blocking. Full
server suite passed 464 tests in 25.31 seconds; two additional preflight cases
were then added and the 30-case vehicle suite passed. Installation is backed up
under `headless_vehicle_adapter/`; no live vehicle was bought or changed yet.
Next native run must resolve the saved test line and depot/models afresh, retain
a fresh pre-mutation save, buy one unassigned vehicle, read it back, then separately
assign, stop/resume and return to depot with readback after each operation. Native
callback success is not proof of actual depot arrival or passenger operation.

Subsequent fresh-load native vehicle acceptance passed on the test map. One
Citaro G1 (31897; quote 1,087,392; sandbox infinite money) was bought at Batley
depot 45146, independently observed unassigned in depot, assigned to test line
75205, stopped, resumed and returned without selling. Readback confirmed the
stop flag transitions, matching line, noPath=false, GOING_TO_DEPOT followed by
IN_DEPOT and membership in the depot's vehicle list. Each of five mutations was
submitted once, all responses independently matched native stdout frames. Fresh
pre-vehicle save was copied/hashed. The test line also survived the user's prior
save/reload. No GUI input or speed changes; vehicle save/reload persistence,
actual passenger service, other carriers and cargo editing remain unverified.
Evidence: `headless_vehicle_adapter/acceptance.json` and `RESULT.md`.

## Bounded request transport

`server/src/tf3_mcp/headless.py` and `headlessTick()` reuse the existing UI/log
command whitelists, query handlers, engine construction event, preview tokens,
durable engine duplicate suppression and response frames. No panel input/click is
needed. This does not add arbitrary Lua, demolition, save or speed operations to
the accepted command set. The original userdata transport is not used as fallback.

Install with `scripts/install_headless_diagnostic.py --mod-content <installed
content/tf3_mcp_bridge> --evidence <output directory>`, then load the test save.
The installer backs up the installed script and creates a new random generation
of 1024 pre-indexed empty Lua resources. Each slot is read once at two-second
intervals, including empty slots: approximately 34 minutes per generation. It
stops at exhaustion or errors, does not refill/recycle slots, and never reloads
the game. Production source defaults to `HEADLESS_GENERATION="disabled"`.
Install a new generation for another acceptance session; do not reuse a generation
after reloading. This finite acceptance mechanism is not a production long-lived
queue. Post-load file discovery remains unverified.

Set `TF3_MCP_HEADLESS_MOD` to the installed `content/tf3_mcp_bridge` directory.
The MCP tools are `headless_status`, `send_headless_request`, and
`read_headless_result`. Engine requests use `kind="build"` and require the current
`expected_session`, independently checked against live map queries. Existing
`build_*` commands in this whitelist only preview; `commit_*` performs the actual
authorized operation with a same-session, unused preview token.

The host records and fsyncs intent before atomically publishing UTF-8 content,
uses the public `warehouse_batch.lock`, permits only one unresolved request, and
persists log anchors/IDs for result reading after server restart. Timeouts or
log/session replacement never authorize resubmission. A received error is retained;
the engine separately preserves unresolved-commit blocking. The lock is per tool
call, not a transaction covering an entire planning/build workflow.

Validation: 56 relevant tests pass, including a mocked end-to-end headless query,
warehouse preview/commit/readback, engine duplicate delivery, stale-session
rejection, shared-lock exclusion, publication failure with durable intent, and
result recovery after host restart. Native acceptance on 2026-10-09 additionally
completed 26 requests with independently matched stdout responses, zero GUI
inputs, and no unknown outcomes. Response median was 1.962 seconds, maximum
2.403 seconds (ticket-file to response-file wall time, not engine CPU timing).
An 80 m standalone road (two edges) and one 500-capacity warehouse were built
once and independently read back. A colliding road preview was rejected without
submission. A newly started MCP process recovered the original warehouse commit
response without resending the request. Game speed remained 4 throughout sampled
states; no speed or reload command was issued.
Current installation and MCP acceptance driver evidence are in
`output/live-validation-20261009/headless_operations/`. The driver starts with
state/map/towns/finances/facilities only; construction specs are supplied after
current-map review and a pre-build save. See `headless_operations/RESULT.md` and
`acceptance.json` for the completed run. The driver has stopped; the bounded
receiver retains its existing slot exhaustion limit. Post-build save/reload,
long-term simulation, external road routing, warehouse delivery operation, and
other construction families were not certified by this transport acceptance.

## Live first-read result

2026-10-09 15:41:37–15:42:37 +08:00, build 40420: both previously unread
resource paths returned their externally written nonce in the same GUI session
`31210.921:table: 000000AEFE8F7B70`. For each slot, the game first logged ready;
the host then atomically replaced and independently read back the marker file;
the game subsequently logged the exact new marker. There were zero GUI inputs
and zero game commands. The watcher completed, restored both files, and disabled
future probe initializations. Independent readback confirmed the installed script
and markers match disabled source.

Evidence: `output/live-validation-20261009/headless_transport/first_read_result.json`,
`first_read_live_log.txt`, and `first_read_acceptance.json`.

The earlier marker test established a UI-independent external data ingress for previously indexed,
unread mod resources. It does **not** establish discovery of files created after
startup, polling of missing paths, safe reuse of consumed paths, or sustained
operation. Actual query/build dispatch was subsequently verified above. No second
reload was needed to complete that marker test. The implementation must retain
existing validation/preview/engine deduplication and log responses, bind requests
to the current session, and stop on unknown outcomes without resubmission.

## Native loader findings and next experiment

Static inspection of installed build 40420 (EXE SHA-256
`74861ac43b041aebc5179154345b3cf1ec83154c8e6cc58e0d9e02ff5fa602e4`)
establishes an additional native cache before file access. Addresses below are
RVAs, not callable interfaces:

- `resolveutil.loadfile` registration at `0x2faf9e1` leads through its closure to
  `0x2fac4d0`. At `0x2fac5cd` it probes object `0x3ceb220` with the normalized
  resource path. A hit bypasses the provider's file existence/read callbacks.
- `0x2fafa80` loads a buffer from that path-keyed cache. On a cache miss,
  `0x2fa96a0` reads/compiles the resource, then `0x2fafcf0` stores a dump of the
  compiled Lua function. The dump writer reaches `0x2fe27b0`, which writes the
  Lua binary signature `1b 4c 75 61`. This is a native bytecode cache, distinct
  from `package.loaded` and `_ug_loadedModules` in `base/init.lua`.
- `0x2faff30` / `0x2faaa00` iterate cache entries and invalidate those missing
  from the provider or whose provider metadata changed. Located direct callers
  are Lua state initialization/reload paths, including a function containing
  `Reloading Lua StateProvider`. No callable mod-side invalidation entry has
  been established. The reference scan is limited to identified x64 patterns;
  it does not prove that other indirect callers do not exist.

Evidence is under `output/live-validation-20261009/headless_transport/native/`
and `native_userdata_analysis/fn_*.txt`. No process memory, executable, game state,
global cache, or native userdata directory was modified during this analysis.

The new experiment uses two previously unread paths, each consumed once, rather
than replacing an already cached path. Each GUI update sequence first emits a
session-bound ready log, waits 30 clock seconds, then reads one marker. A bounded
host watcher replaces the appropriate mod-owned file after the ready log and
requires exact nonce confirmation in the same session. Both files are restored
on normal completion, timeout, or handled interruption. Errors and late ticks
stop the test without replay; no payload reaches command dispatch.

Source/release flag `ENABLE_FIRST_READ_PROBE` defaults to false. A diagnostic
installation can enable it for a single fresh script initialization. The two live
confirmations above establish only
first-read ingress: resource indexing, finite cache growth, slot exhaustion,
reload/session identity, and command at-most-once handling remain design gates.
Never treat the experiment as an operational unlimited request queue.

Validation: 49 relevant mocked tests pass, including delayed first reads,
distinct paths, no dispatch, disabled defaults, error stopping, and expired-window
stopping. They do not establish live VFS freshness. The watcher and result are
`headless_transport/watch_first_read.py` and `first_read_result.json`.

2026-10-09 15:27:11–15:29:11 +08:00: the current GUI session performed 120
resource reads. It reported `baseline_v1` on its first read. The external watcher
atomically replaced the file with a unique marker, and the changed disk contents
were independently read back. The game never reported that marker and finished
with `reads=120`. Thus this fixed resource path does not provide a working dynamic
inbox in build 40420. The native bytecode cache above explains why repeated reads
of a loaded path do not reach the file provider. No game command or
GUI input was issued. The watcher was stopped and the original marker restored.
Evidence: `output/live-validation-20261009/headless_transport/resource_probe_result.json`
and `resource_probe_log.txt`.

Do not implement command dispatch by repeatedly overwriting that cached path or
repeat the same failed experiment. Existing panel/log transport remains available.
First-read ingress and bounded dispatch were subsequently verified above. Native
extension/debugger integration was not used; no native executable/memory patch
or global cache clearing was necessary.

2026-10-09 15:22:51 +08:00: fresh GUI startup on build 40420 reports
`resolveutil.loadfile` and `resolveutil.resolve` as functions. Installed
`base/content/base.zip`, entry `base/init.lua`, uses
`resolveutil.loadfile(resolved)` to obtain a chunk, then executes it. Its module
cache is maintained outside that call. This establishes the call shape, but does
not prove the native file loader sees updates during a running session.

The earlier, now disabled experiment polled only the mod-owned `ingress_probe.lua`, once
per second for at most 120 seconds after GUI initialization. It accepts only a
short marker string and never routes it to game commands. It stops on the first
loader/validation error, and does not change global caches. A bounded host watcher
waits at most ten minutes for the fresh baseline marker, atomically replaces it
with a unique marker, checks an observation from the same GUI session, and restores
the baseline file. Results are in `headless_transport/resource_probe_result.json`.
44 relevant tests pass, including changed data, throttling, end-of-window stopping,
invalid data rejection and no native command dispatch. These are mocked checks.

The user requested automatic external dispatch without panel input/clicks on
2026-10-09. Existing UI event routing, command validation, preview tokens, engine
deduplication and log responses can be reused if a suitable ingress is verified.

Inspected the current build's `api/tealdef` and official API documentation:

- https://wiki.transportfever3.com/script-doc/app.html
- https://wiki.transportfever3.com/script-doc/main.html
- https://wiki.transportfever3.com/doku.php?id=modding:general:syntax

No external HTTP/socket listener or live resource-file reader was found in those
definitions. This is a search result, not proof no such mechanism exists.
The live startup log reports `io=nil`, but lists `ug`, `require`, `package`,
`resolveutil`, `ug_require`, and `ug_require_cleanup`. Merely importing a module
does not prove it can supply changing requests; caching and resource indexing
remain unverified. Do not clear global caches or substitute another native
feature's userdata directory to claim success.

`probeEnv()` now records only types of relevant globals and direct member names/types.
It does not invoke these functions, load libraries, read files through undocumented
APIs, dispatch commands, or log package paths. On a fresh GUI script initialization,
the ordinary startup log emits `transportDiscoveryVersion=1` automatically.
No panel request is necessary for this diagnostic. Installing the source does not
update the already-loaded Lua script; the user must reload before live inspection.

Validation: 42 tests passed across transport discovery and existing UI/log,
construction, road, air, and access suites. Native capabilities are mocked in these
tests. Deployment hashes and the previous script are retained in
`output/live-validation-20261009/headless_transport/`.

Those capability/first-read investigation gates have now passed. Remaining work
for a long-lived production transport includes safe slot replenishment or a
verified uncached ingress, post-reload continuity, and broader native operation
coverage. Preserve session binding, one request in flight, durable intent,
expiry, deduplication and unknown-outcome blocking. Do not replay pending panel
requests or construction scripts. Original userdata transport remains set aside.
