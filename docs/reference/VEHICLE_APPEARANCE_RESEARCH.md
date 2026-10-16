# 载具改色与涂装可行性调查

2026-10-16。依据本机游戏原生 API 定义、原生 GUI 调用和官方 Wiki；仅调查，没有修改车辆、安装涂装或提交游戏命令。调查时桥接尚无外观修改工具，以下可行不等于实机验收。后续已实现的第一阶段接口见[载具外观与改色](VEHICLE_APPEARANCE.md)。

## 能力结论

| 需求 | 结论与边界 |
|---|---|
| 已购载具统一改色 | 原生有明确入口，可封装 MCP；受模型改色遮罩限制 |
| 多辆车或某线路车辆统一改色 | 原生管理器逐车调用同一命令，可按当前真实车辆列表封装；不是原生原子批量事务 |
| 按线路颜色给车辆配色 | 可读取线路颜色后应用到车辆；持续自动同步还需要另行实现触发逻辑 |
| 购车时指定颜色 | `VehiclePart.color` 配合 `makeVehicleBuyCmd` 有原生配置路径，现有购车工具需扩展 |
| 每节车厢不同颜色 | 配置结构支持逐 part 的 color；未找到独立的单节改色命令，不能把整车改色命令当作逐节命令。现有车可能需要配置替换，须验证费用、年龄、维护、货物与线路状态 |
| 切换已经安装的涂装车型 | 涂装通常是另一个 modelId；原生有 VehicleReplace 配置替换路径，需确认载具兼容、可用性、价格及状态保留，不等同于免费原地贴图切换 |
| 新增自定义图案、Logo、广告 | 官方支持制作 repaint 模组，使用新 mdl、mtl、贴图和 UI 图标，复用原模型网格；需适配 UV、材质及所有 LOD |
| 运行中给任意单车传入 PNG/URL 换贴图 | 本次未找到受支持的通用载具接口；不能承诺无需资源加载、无需模型变体的单车动态换图 |

## 原生代码证据

本机根目录：`E:/SteamLibrary/steamapps/common/Transport Fever 3`。

- `api/tealdef/api/cmd.d.tl:657-662`：`makeEntitySetColorCmd(entity, color)`，参数为 RGB `Vec3f`。
- `base/content/gui.zip` 内 `gui/entity_window/vehicle/vehicle_eow.script.tl:132-150`：检查 `noCblendMask`，游戏载具窗口的 Change Color 按钮直接发送上述命令。
- 同包 `gui/line_vehicle_mgmt/manager_window.tl:4895-4920,5068-5077`：检查所有选中载具的模型 `metadata.transportVehicle.noCblendMask`，跳过不可改色车辆，逐车发送命令。
- `api/tealdef/api/type.d.tl:1503`：`VehiclePart` 包含 `modelId`、`reversed`、`compartment2loadConfig` 和 `color`；`TransportVehicleConfig` 包含各车辆部件。
- 同包 `gui/line_vehicle_mgmt/vehicle_util.tl:8-26`：创建车辆部件时可赋值 `part.part.color`。
- `api/tealdef/api/cmd.d.tl:892,898`：购买与替换命令接受 `TransportVehicleConfig`；同包 `gui/line_vehicle_mgmt/vehicle_react_util.tl:407` 使用原生替换命令。
- 同包 `gui/line_vehicle_mgmt/vehicle_store_util.tl:177-179`：用 `groupFileName` 对车型变体分组。分组不证明其容量、货品或运行参数完全相同。
- `api/tealdef/api/type/transformator.d.tl` 的 `setAlbedoTexture`、`setNormalMapTexture` 参数是 `ParticleSystem`，不是任意载具车身贴图接口。

## 官方资源机制

官方 [Repaint Mods](https://wiki.transportfever3.com/doku.php?id=modding:vehicles:repaints) 给出 eCitaro 涂装示例，说明新涂装需要模型变体、材质、贴图和图标；材质引用必须在各 LOD 中正确关联。另做变体可以让原版车型与新涂装并存；若覆盖共享材质，不能将影响限制为一辆车。

官方 [Material Definition](https://wiki.transportfever3.com/doku.php?id=modding:general:resourcetypes:mtl) 说明改色依赖材质颜色混合遮罩，贴图接受 DDS/TGA。因此 RGB 改色只能改变模型允许的区域，无法直接生成文字、车标或任意图案。贴图热加载与现有车辆变体替换效果仍需单独验证。

## 建议实施顺序

1. 只读 `get_vehicle_appearance(vehicle)`：读部件、颜色、模型资源、改色能力；未知字段明确标记。
2. `set_vehicle_color`：仅使用原生改色命令，校验当前会话、归属、RGB 和遮罩；保存原值、单次提交并独立读回，不以命令回执代替成功。
3. 多车/线路配色：逐车独立回执，保留部分成功，不重发未知结果；独立于只读批处理协议。
4. 涂装资源列表和原生配置替换：先实现兼容、费用及状态差异检查，再做单车实测；最后再支持自定义涂装资源制作。

第一阶段不必等待自定义贴图制作完成。整体可封装成 MCP 工具，但目前只完成源码与文档可行性核对，没有现场效果或保存重载验证。
