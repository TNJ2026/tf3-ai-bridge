# 奔驰 Urban eTruck 全面强化版

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
