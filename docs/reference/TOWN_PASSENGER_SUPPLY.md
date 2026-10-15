# 城市供给面板的旅客项

`get_town_cargo_supply(town, include_passengers=true)` 在原货品结果之外返回
`passengers`，要求接收器能力 `townPassengerSupplyVersion=1`。省略参数保持原行为。

依据本地游戏 `game_mechanics/towns/town_util.tl` 的
`getCargoSupplyDemandsLandUseWithResidentialLineUsage`：

- 需求为 `getLandUsePersonCapacities(town)[RESIDENTIAL + 1]`。
- 供给为 `round(需求 × clamp(getTownLineUsage(town) × 2, 0, 1))`。
- `supplyRate` 为面板供给／需求；同时保留 `rawLineUsage` 和倍率。
- 零需求时原生面板不显示该行，本接口不编造供给或比例。缺失或无效数据报错。

这是原生面板由公共交通线路使用率折算的旅客指标，不是累计登车人数，也不限定公路公交。
它与车辆当前在载旅客数、站点当前候车数不同，时间窗口未知。不得将三者混算。
用户要求以此面板口径估算公交增量时，估算属于规划假设，投运后仍需同口径读回。

2026-10-14：已完成 22 项离线测试和六种 Lua 运行时编译检查，已备份并更新当前
staging 接收器文件，保留原 generation。当前游戏仍加载旧接收器，尚无实时旅客结果；
须保存当前进度并重新载入后，核对新会话、主城与能力再调用。未自动读档或购买公交。
