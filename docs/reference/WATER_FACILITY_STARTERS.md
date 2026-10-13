# 港口、船坞与水上维护设施新建入口

2026-10-13 最新选型规则：新建码头优先小型，只有船型、必要功能或有依据的容量需求无法满足时才选更大规格，见[水运选型指南](../strategy/TRANSPORT_WATER_SITING.md#码头规模优先小型2026-10-13)。本入口现已支持 `harbor_size="small"|"large"`，默认 small；当前测试地图的小型新建、平台扩建和新增小型登陆处均已原生施工并独立读回。港口请求要求接收器心跳 `waterHarborLayoutVersion=1`，旧接收器在发送前拒绝，不静默回退大型布局。详见[实测记录](../../output/harbor_small_20261013/RESULT.md)。

2026-10-11：`build_water_facility(kind,x,y,z,rotation=0)` 已实现，指纹修订后在盘锦副本完成三类设施原生施工及配置读回。需要接收器心跳 `waterFacilityVersion=1`、`waterFacilityFingerprintVersion=2`；旧接收器在发布请求前拒绝，不回退任意Lua或旧施工脚本。

## 原生初始布局

| kind | 内容 | 资源 |
| --- | --- | --- |
| harbor，small（默认） | 5模块：1个small_pier小型登陆处、1块小型码头平台、1座小楼及2个人行入口；支持SMALL_SHIP客货装卸 | `::/stations/water/harbor_modular.con` |
| harbor，large | 7模块：1个medium_pier大型登陆处、原生大型主楼/平台及4个人行入口；支持SHIP/SMALL_SHIP | `::/stations/water/harbor_modular.con` |
| shipyard | 模块为空的原生购船船坞 | `::/depots/water/water_depot.con` |
| maintenance | 模块为空的原生船舶维护站，原生设计维护池12、半径1400米 | `::/depots/water/water_maint_station.con` |

港口两种初始布局均逐项对照当前安装包的 createTemplateFn（smallterminals=1 / largeterminals=1）。`passenger_dock_50_12.module` 的原生名称是“小型码头”（平台）；`small_pier.module` 是“小型登陆处”（船舶终端），`medium_pier.module` 是“大型登陆处”。平台和登陆处是不同模块。资源名中的 passenger_dock 不表示只能客运；新址仍读取实际终端客货标志及运输模式。harbor_size 仅适用于 harbor，其他 kind 传入将被拒绝。

该入口不创建仓库、货车站、接路、运输线路或车辆。砂运上岸仍须验证码头和货车站覆盖同一真实仓库库存，仓库按STOCK_LIST去重。船坞不能替代独立维护站；购船、维护、通航分别验收。

## 操作契约

1. 确认当前会话、地图、资金、无pending和施工授权；保留独立施工前存档。当前用户已授权在本测试地图直接施工验证，无需另建独立副本；此授权不自动扩展到其他正式地图。
2. 明确放置高程z与旋转角。当前原生水运设施参考位置为水面高程加2米；盘锦实测水面0，三类设施在z=2取得原生预览通过，z=0曾与WATER_MESH碰撞。此偏移仍须按原生模板和新址核对。入口不按“中心必须在水上/陆上”提前否决岸线设施，由原生布局检查水陆适配和碰撞；预览不等于通航。
3. 预览验证资源、模块类型、年代、许可和近距离重复设施，返回60秒单次令牌。原生错误、碰撞及未知移除均阻止提交。
4. `commit_facility(preview_token)` 消耗令牌后重查资源、模块、会话与碰撞，单次提交并读回配置。资源变化、过期、已用令牌均拒绝，未知结果不重发。
5. 返回configurationVerified仅表示配置匹配；serviceVerified与navigationVerified保持false，施工验收另查原生终端/船坞/维护能力；实际投运按当前任务所需的航路、维护、共库及统一载具出发标准验收，不把常规完整往返作为门槛。不能把配置通过作为供货成功。

## 加载与当前验收边界

Python MCP入口须刷新MCP进程才能出现在工具清单；本地新Python进程可使用相同具名headless协议。游戏侧新命令和版本标记需重新载入存档，不能只刷新MCP就声称游戏已更新。禁止自动重载；按项目AGENTS与执行手册取得用户重载授权或由用户手动加载。

专项测试覆盖原生模块槽位、三类预览/单次提交、资源/许可/碰撞/重复/未知参数拒绝、旧接收器前置拒绝。安装包模板离线执行与槽位逐项比较通过；六种Lua运行时及16个额外局部变量余量编译通过。证据位于`output/water_facilities_20261011/`。

盘锦隔离副本首次码头提交曾被配置指纹校验拒绝，未进入applyProposal。用户加载修订接收器后，原请求正式对账，重新预览后码头65569、船坞65575、维护站65578各单次施工并独立读回通过。港口与岸边货站共用真实仓库27493、容量500；已购货船装60砂返港卸货，玻璃厂已有8玻璃。四向航路完整验收和家具城市交付不能由配置读回推断，按output/water_facilities_20261011/RESULT.md及completion.json记录的实际边界判断。

2026-10-11 指纹修订：脚本描述符按fileName及lossless params比较，不把原生userdata包装地址或包装方法当作配置；metadata与模块数据拒绝不支持的非无损对象，不序列化地址兜底。心跳新增waterFacilityFingerprintVersion=2。原生包装对象回归用例重现并覆盖假变更，真实参数变化仍阻止提交；修复后已完成上述三类实机施工，不代表所有布局或长期模拟安全。

新增受限headless命令reconcile_facility_rejection(request_id)，仅接受durable ledger中commit_facility的精确前置错误“facility changed since preview; inspect and preview again”，并核对存在的响应缓存。保留原请求及错误，记录reconciled_rejected和retryAllowed=false；不接受原生失败、超时、缺失错误、其他命令或冲突证据，不重放旧令牌。此入口本身不施工，不替代新鲜地图调查和预览。加载异常现场存档后先核对原pending，再显式对账；不能用读旧档或清空记录绕过未知施工结果。


## 小型码头新建和扩建实测（2026-10-13）

在用户授权的当前测试地图，从零建成码头39818：位置(-2450,-962.5,2)、旋转180度。原生新建预览报价720897元，无碰撞、警告及放置阻塞；单次提交后5模块、1个SMALL_SHIP客货终端独立读回。

随后按当前原生空槽102009801增设 `passenger_dock_50_12.module`，读回6模块；重新读取扩建后空槽104009736，再增设 `small_pier.module`，读回7模块和2个SMALL_SHIP客货终端。上述槽位仅为本布局证据，其他设施必须重新查当前槽位、资源类型及空占状态。

扩建沿用 `preview_facility_module` → `commit_facility`。现有替换预览为 **structural_only=true、collision_checked=false**，没有完整原生报价；不能伪称完整碰撞预览通过。两种增补模块的原生基础价格各60000元，不含未知地形/替换成本。本次利用用户对测试地图任意建拆的明确授权进行受控单次提交，由引擎严格校验；不作为普通限额工程绕过报价或碰撞要求的依据。不要调用可能因移除冻结道路而断言的原生替换 makeProposalData。

已保存固定完工槽并恢复原4倍速，无pending、未恢复监控。未购船、未做实船航行或长期模拟，不宣称供货、通航或共库已验收。回归87项、编译12组通过，原生小/大模板离线槽位匹配；本轮大型布局未新建。详细请求及证据见实测目录。


2026-10-13 补充不同岸线复测：坡岸40573与低平弯岸40550两座小型码头均从零新建，完整原生预览、单次提交、5模块及1个小型船客货终端独立读回通过。坡岸陆侧25米抬升约8.8米，低平岸后约1～4米；没有单独平整，但有原生建造地形调整。完整报价分别737565/720613元；已保存、恢复4倍速、无pending。未做外接道路、实船或长期模拟。[两岸线验证记录](../../output/harbor_terrain_20261013/RESULT.md)。
