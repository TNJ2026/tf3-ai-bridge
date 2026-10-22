# 奔驰 Urban eTruck 全面强化版

> 2026-10-20：本文为历史记录。对应加强道路/强化车辆已从当前模组移除，见[移除范围与备份](ENHANCED_ROADS_VEHICLES_REMOVAL.md)。

用户后续要求从原版重新复制的新车型见[Urban eTruck 800独立副本](URBAN_ETRUCK_800.md)（v0.12.103 / revision79）。新车型不沿用本文旧全面强化或Logo配置。


## 车厢侧面 Logo（2026-10-20）

本地版本 0.12.88 / revision 64 为现有强化车型加入 `assets/repaints/logo.png`，原版车型保留。两侧均放在侧门后方的连续车厢面板上，按模型空间等比例烘焙到原版 UV；每侧约 3.18 × 2.46 米，占侧板高度约 96%，上下各留 5 厘米。仅裁去源图透明外边，不裁切 Logo 图形，两侧文字方向一致。

模型改用独立的 `mat/urban_etruck_logo.mtl` 与 `mat/urban_etruck_lod_logo.mtl`，近、远 LOD 共用独立贴图；Logo 区域移除车辆改色蒙版，保留其余污渍、锈迹及原版法线等资源。性能参数、网格、动画及原版车辆不变。购买缩略图仍为原版外观。

复现工具：`scripts/build_urban_etruck_logo.py --archive <urban_etruck.zip> --logo assets/repaints/logo.png --output <新目录>`。工具只生成贴图及材质，不修改游戏文件。使用项目的 Python 环境，依赖 Pillow、lupa。

已备份并同步源码与本地 staging 副本，保留接收器配置和线上绑定；Lua 资源、TGA 纵向转换往返、3 个 LOD × 2 侧 × 9 点的映射覆盖及发布目录检查通过。侧板预览是按实际 UV 反投影的离线预览，不是游戏截图。未重载、上传、替换车辆或恢复监控，实机外观待加载后验收。证据与备份：`output/urban_etruck_logo_20261020/`。

## 初始强化配置

2026-10-17，0.12.49 / revision 25。独立复制原版 `::/vehicle/truck/urban_etruck/urban_etruck.mdl`，保留原版。

新资源：`tnj_tf3_ai_bridge::/vehicle/truck/urban_etruck_test/urban_etruck_test.mdl`。
显示名称：奔驰 Urban eTruck（100容量 · 全面强化）。配置文件：`mod/tf3_mcp_bridge/content/vehicle/truck/urban_etruck_test/urban_etruck_test.mdl`。

“最大”采用此前全面强化测试档，并非已知官方上限。

| 属性 | 强化配置 |
|---|---:|
| 目标游戏显示容量 | 100 |
| cargoEntry 原始容量 | 400 |
| 最高速度 | 800 km/h |
| 功率 | 20000 kW |
| 牵引力 | 4000 kN |
| 装卸速度 | 500 |
| 空重 / 最大载荷重量 | 1000 / 2400 kg |
| 弯道速度系数 | 100 |
| 摩擦 / 制动减速度 | 0.001 / 25 |
| 价格 / 运行费参数 | 1000 / 100 |
| 寿命参数 | 365000 |
| 起始年份 | 1850 |
| 噪音 / 污染 | idle、speed、power均0，移除score |

容量按此前货车实测的原始值1/4折算设置；本车型显示100尚需原生目录读回。装载可视化capacity=72保持原值，避免改变货物模型布局。保留电动引擎、UNIVERSAL货物类别、TRUCK模式、原版外观、动画、声音、灯光及尺寸；货车不添加客运舒适度。实际车速受道路、路径和曲线等限制。

已验证Lua执行、关键字段、82个唯一直接资源引用（含.lua/.tl脚本资源解析）、5个原版重命名图标，以及源码/staging逐文件一致。发布目录检查48文件、无问题；正式接收器和线上绑定保留，元数据版本同步。未重载、购车、替换车辆、上传或恢复监控，未完成原生加载和行驶验收。

证据及模组外备份：`output/urban_etruck_20261017_184438/`。
