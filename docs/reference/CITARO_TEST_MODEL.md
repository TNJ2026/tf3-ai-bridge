# Citaro G1 独立测试车型

## 当前配置：全面强化测试（v0.12.37 / revision 13）

2026-10-17 用户明确要求全部强化，包括容量及经营属性。已备份并同步源码与本地 staging，Lua解析及逐文件读回通过；**尚未重载，此表是磁盘配置，不能作为当前游戏实测值**。原资源ID保持不变，名称改为“Citaro G1（800 km/h · 全面强化测试）”。以下数值是人为选定的测试档，不是官方最大值。

| 参数 | 本次配置 |
|---|---|
| `landVehicle.topSpeed` | 800 / 3.6 m/s |
| `engines[1].power` / `tractiveEffort` | 22000 kW / 3000 kN，原版100倍 |
| `curveSpeedScale` | 100，效果待原生加载实测 |
| `weightEmpty` / `weightMaxPayload` | 1500 / 1980 kg |
| `friction` / `brakeDeceleration` | 0.001 / 25 |
| 客舱原始 `capacity` | 1120，原版10倍；按此前游戏折算预计280，待读回 |
| `loadSpeed` | 300，原版100倍 |
| `comfortFactor` | 1（官方范围0～1） |
| `emissions.noise` / `pollution` | 移除自动score，显式idle、speed、power全为0 |
| `cost.price` / `maintenance.runningCosts` | 1000 / 100，显式配置，待原生读回 |
| `maintenance.lifespan` | 365000（原21915） |
| `availability.yearFrom` / `yearTo` | 1850 / 0 |

外观、车体尺寸、车门动画、声音、客运类型和设施兼容保持。未随意改动未使用的priceFactor/maintenanceFactor，也未压缩车门动画等待。零排放配置不代表音频静音或排烟粒子消失。道路、站内车道及交通规则继续适用，不能承诺实车达到800。

官方字段依据：[车型物理](https://wiki.transportfever3.com/doku.php?id=modding:vehicles:types)、[容量、排放与舒适度](https://wiki.transportfever3.com/doku.php?id=modding:vehicles:basics)。备份与验证：`output/citaro_full_20261017_121959/`；执行脚本 `scripts/update_citaro_full_test.py` 是从v0.12.36升级的一次性脚本，有版本及旧值断言，不应重复运行。

## 历史配置与验证（v0.12.36）

2026-10-17：v0.12.36 / revision 12，源码与本地 staging 已部署，并按用户授权通过 MCP 保存当前进度、独立备份及单次重载。时间/玩家/世界精确核对通过，读档前后地图摘要一致，无未决请求，保持原暂停状态。原生可购车型列表已包含测试车型（本会话模型ID4504），最高速度222.222229 m/s、容量28、自动价格5,918,754；原版车型同时保留。尚未进行商店像素验收、购车、外观试跑或装载速度实测，现有载具未替换。

名称：**Citaro G1（800 km/h · 10倍装载测试）**。

资源：`tnj_tf3_ai_bridge::/vehicle/bus/mb_citaro_g1_test/mb_citaro_g1_test.mdl`。

源码：[mb_citaro_g1_test.mdl](../../mod/tf3_mcp_bridge/content/vehicle/bus/mb_citaro_g1_test/mb_citaro_g1_test.mdl)。

| 参数 | 原版 | 测试车型 |
|---|---|---|
| `metadata.landVehicle.topSpeed` | 22.222 m/s，约80 km/h | `800 / 3.6` m/s，800 km/h |
| `metadata.transportVehicle.loadSpeed` | 3 | 30 |

除显示名称和这两个参数外，规范化资源引用后完整Lua结构比较无其他差异。原版相对网格、材质、动画及共享声音/变换器路径改为显式基础游戏命名空间 `::/`，共134个唯一直接引用已核对本机原生文件或归档条目存在。复用原版美术资源，不复制网格和材质；5个原版图标按新模型文件名复制，以支持按模型名查找图标。

容量、动力、牵引力、重量、排放、舒适度、维护配置及可用年份保留。容量仍由原版参数与游戏规则计算，不能把模型原始112与游戏显示28混为同口径。价格配置仍为 `price=-1`（自动计算），提高速度可能改变实际购买价，不能保证价格不变。

本车型基础速度已经800 km/h，不应无意再叠加此前原版单车的10倍修正，否则理论上限会再次放大。既有原版车不会自动获得新车型的装载参数；购买或替换须另行预览、备份及核算，不使用只允许机械属性相同的涂装替换接口绕过限制。

`loadSpeed=30` 是原参数的10倍测试值，不是官方最大值，也不保证实际上下客总耗时恰好缩短至十分之一；开关门、站点兼容等因素仍需实测。基础速度同样不代表动力、道路或弯道允许实际达到800 km/h。

离线验收：Lua解析成功、结构差异仅预期三处、134个直接资源引用存在、源码与部署模型字节一致、正式接收器离线包检查通过。证据及模组外备份：`output/citaro_variant_20261017_120934/`。这不是原生加载、Mod Hub发布校验或实车验收。

后续原生加载证据：同目录 `reload_result.json`、`loaded_models.json`。上述离线验收本身不替代原生校验；此次车型列表读取确认资源已注册且最高速度正确，列表不返回 `loadSpeed`，因此30仍是已部署模型参数，不冒称装载效果已实测。
