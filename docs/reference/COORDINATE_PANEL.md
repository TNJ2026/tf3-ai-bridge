# 游戏内鼠标坐标面板

## 当前行为

坐标面板默认隐藏（`PANEL_VISIBLE = false`），底部信息栏不显示坐标控件。仅隐藏显示，原生扩展注册、同步 `react.onStep` 坐标采样、状态更新、异常诊断和完整面板实现均保留。隐藏分支返回没有子控件的 `BoxLayout`，不会停止采样。

保留的显示实现使用中英文提示，坐标保留一位小数，单位为米；X/Y 为世界平面坐标，Z 为地面高度。没有游戏内显示开关。不包含镜头定位、施工、改速或存档写入。

文件：

- `mod/tf3_mcp_bridge/content/tf3_mcp_bridge/gui/coordinates.res.lua`：原生扩展资源注册。
- `mod/tf3_mcp_bridge/content/tf3_mcp_bridge/gui/coordinates.script.lua`：隐藏开关、GUI 面板和只读采样。
- `mod/tf3_mcp_bridge/content/tf3_mcp_bridge/gui/coordinates.css.lua`：局部样式。

离线回归覆盖默认隐藏时不创建坐标控件且采样继续，以及启用保留显示分支后的行为；这不等于实机像素验收。英文游戏测试范围见[英文兼容验证](ENGLISH_COMPATIBILITY.md)。GUI 资源修改需要重新加载后生效，不自动读档或恢复监控。

## 开发阶段记录（2026-10-12）

以下按当时的实现与验证状态保留，涉及常驻显示、折叠或待重载的描述均不是当前行为。

2026-10-12：用户已确认坐标可正常显示。按最新要求改为单行常驻、移除展开／折叠按钮，并在信息栏扩展项目中排到最右侧；新布局已安装，待重新加载显示。

面板使用游戏原生 `GameBarInfoDisplayExtension`，在底部信息栏常驻单行显示 `X  12.3    Y  -45.6    Z  7.8 米`，没有展开／折叠按钮。原生 `getPlugins` 按 `order` 升序排列；本项设为 10000，排在现有信息项之后。在同步 GUI `react.onStep` 回调中读取鼠标地面坐标，仅当显示文本变化时更新状态。保留一位小数，X/Y 是世界平面坐标，Z 是地面高度，单位都是米。

鼠标未指向有效地面时显示「未指向地面」，不把上次坐标继续当成当前位置；接口不可用时显示「坐标暂不可用」。不包含镜头定位、施工、改速或存档写入。

文件：

- `mod/tf3_mcp_bridge/content/tf3_mcp_bridge/gui/coordinates.res.lua`：原生 React 扩展资源注册。
- `mod/tf3_mcp_bridge/content/tf3_mcp_bridge/gui/coordinates.script.lua`：GUI 面板和只读采样。
- `mod/tf3_mcp_bridge/content/tf3_mcp_bridge/gui/coordinates.css.lua`：局部样式。

实现依据本机游戏 `gui.zip` 中的 `gui/main/react.lua`、`gui/game_bar/game_bar_widgets.tl`、原生 `.res.lua` 描述及 `api/gui.d.tl`；没有修改游戏原文件。仅向已安装桥接模组增加这三个资源，原 `bridge.script.lua` 及其代次保持。

离线验证：三个文件在 Lua 5.1～5.5 和 LuaJIT 2.1 编译通过；模拟 GUI 检查实际格式化、离开地面清空、收起停止读取、重新展开清空、非有限数、负零及接口异常。不是原生渲染验收。证据位于 `output/coordinate_panel_20261012/verification.json` 和 `deployment.json`。

首次原生日志报 `function data() not defined`，位置为 `coordinates.script@Panel`。普通模块 `return coordinates` 不满足此 Lua 资源加载入口；现同时提供 `data()` 返回同一导出表。原检查遗漏了资源导出契约，已补充六种 Lua 运行时的 `data().Panel` 解析检查，并确认旧版本确实缺少入口。修复证据为 `output/coordinate_panel_20261012/loader_fix.json`；通过该检查仍不等于原生显示成功。

再次加载在 2026-10-12 03:09:35 UTC 报 `Recipe child must be a layout`，指向 `TnjMouseCoordinatePanel`：自定义 Recipe 直接返回 `Component`，不满足原生转换约束。现按原生 `GameBarEarningsPlugin` 结构增加外层 `BoxLayout`。回归检查 `scripts/tests/test_coordinate_panel.py` 覆盖资源导出、布局根节点、坐标更新、收起及展开；旧安装版本能复现布局检查失败，修复后的安装副本通过。证据为 `output/coordinate_panel_20261012/layout_fix.json`。离线结构检查无法替代 C++ 原生转换及实际显示验收。

用户已确认同步更新版本的坐标读取正常。最新单行常驻布局的回归检查通过，GUI 资源修改需重新载入；由用户保存当前进度后重载，Agent 不自动重载旧存档。载入后确认单行显示及最右侧排序。

后续用户反馈面板显示「坐标暂不可用」，表明界面已出现，但坐标读取仍未验收。原先 `pcall` 隐藏了异常详情，无法据此判断是接口调用、字段访问还是格式化失败。已安装限次诊断：按阶段记录 `[TNJ_COORDINATES_V1]` 错误，同一错误仅一次，每次界面加载最多三条。回归检查确认读取失败不会破坏面板且重复错误不会刷屏；尚待重载后取得原生错误原因，不能称为坐标读取已修复。

诊断结果：2026-10-12 03:14:28 UTC 原生日志明确为 `hasTerrainPosition: API is currently restricted`，栈落在 `react.lua` 的延迟队列执行处。`onStepTimer` 将回调排入 `enqueueDeferredStep`，鼠标 API 在该上下文受限。已按原生 `gui/layers/layer_react_util.tl` 中 `buildMouseEmissionInfo` 改用同步 `react.onStep`，没有取消或绕过 API 限制。模拟相同上下文限制后旧版无法更新坐标，修正版安装副本通过。证据为 `output/coordinate_panel_20261012/sync_step_fix.json`；本次修复后的原生坐标读取仍待重新加载确认。
