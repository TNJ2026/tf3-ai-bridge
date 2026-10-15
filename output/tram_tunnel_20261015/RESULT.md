# 地下有轨电车道路施工验证（2026-10-15）

用户授权尝试建造并预览验证。当前 Wareham 地图保持暂停，未恢复监控。

- 位置：Wareham 东南侧，沿 y=-2600，从 x=-1350 至 -850；路面高程约1.3～1.55米。采样地表丘顶约13.35米。
- 模板：`town/town_new_small_tram_electrified`，原生双向车道支持 TRAM 和 ELECTRIC_TRAM。
- 隧道资源：`::/infrastructure/tunnel/tunnel_b_car.tunnel`。
- 总长500米：两段150米隧道，加两端各100米地面引道。
- 原生预览成功，无碰撞、警告或消息，报价609814元；声誉影响适配器不支持道路，保持未知。
- 已先保存备份，再刷新预览、单次提交；回调成功且静态验证通过。见 [施工记录](construction.json)。
- 地面边28242、28246，隧道边28243、28245。独立读回确认隧道 type=2、typeIndex=4；地面 type=0。
- 三个连接点28233、28236、28239分别检查两向 TRAM / ELECTRIC_TRAM，12项均为 `pathFound=true`、`directPathVerified=true`。证据为本目录 `path*.json`，几何与车道为 `edge*.json`、`node*.json`。
- 建前/建后即时余额均44415656元，游戏时间均5993800；报价不冒称已实际扣款。不新增贷款。
- 建前备份 `wareham_before_tram_tunnel_20261015`，完工保存 `wareham_tram_tunnel_verified_20261015`，均验证新存档文件成功；未重载。

结论：此模板与隧道资源组合已通过原生预览、施工、独立实体读取和电车双向连接检查。测试段独立，未接入现有运营网络，未购车或实车试跑；不据此声称已投运、长期稳定或支持地下车站及任意隧道岔口。
