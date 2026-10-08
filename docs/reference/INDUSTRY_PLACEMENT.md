# 沙盒产业放置

新增四个 MCP 工具，使用当前游戏加载的产业资源，不硬编码产业种类：

| 工具 | 功能 |
| --- | --- |
| `list_industry_resources()` | 返回沙盒状态及原生 `isIndustry` 建筑资源 |
| `preview_industry(resource, x, y, rotation=0, on_water=false, seed="tf3-mcp")` | 生成原生产业布局并检查碰撞，返回 60 秒有效的一次性凭证 |
| `commit_industry(preview_token)` | 重查沙盒状态、地图身份、布局与碰撞，单次提交 |
| `get_industry_operation(operation_id)` | 独立查询建筑及所属 `INDUSTRY` 组件，不重发施工 |

坐标使用游戏世界 XY，旋转为度。高程、占地和产业内部布局由原生生成器确定。水上产业需显式传 `on_water=true`，最终可行性由原生提案决定。资源存在不代表任意位置均可建设。

实现依据当前游戏自带 `gui/map_editor/map_editor.tl` 的 `createIndustries` → `createIndustryProposal` 流程；使用 `api.type.Map.Industry` 与 `api.engine.terrain.makeMapFromGame`。实机 `makeProposalData` 仅接受 `SimpleProposal`，与 Teal 标注存在差异：将生成器确定的资源、变换和完整产业参数转为简化提案，对同一提案类型预览和提交。预览和提交均要求 `api.res.getBaseConfig().sandboxMode == true`。保留所有现有产业，拒绝生成器移除、提案替换、现有道路修改和未知碰撞。提交不使用 `ignoreErrors`。

调用前须按项目规则保留独立存档。预览不修改世界；提交会建设产业及原生提案包含的内部结构和地形调整，不额外铺设外接道路、线路或购买车辆。建设后仍需分别验收接路、生产、供给及持续模拟。

提交回执 `verified=true` 仅表示独立读回发现了目标建筑及其产业组件。`pending_or_unconfirmed` 或工具超时不能判为未建成；保留 operation_id 并查询实际地图，不重新提交。凭证消费后不能复用。桥接重载会失去内存中的凭证和操作记录，返回 `unknown_or_bridge_reloaded` 时需要现场对账。

验证：真实 Lua 桥接在模拟原生 API 下测试沙盒门禁、碰撞、现有道路保护、地图变化、布局变化、过期凭证、一次性提交、延迟回调、产业组件读回及 MCP 路由。2026-10-06 经用户明确授权，在当前沙盒图逐类放置全部 27 类产业，逐项独立读回建筑、产业组件、库存及生产规则；原有 17 处产业保留。证据见 [实机测试记录](../../exports/industry_placement_test_20261006/RESULT.md)。短时模拟复查不证明长期模拟安全，也不等于运输和城市供货验收。

加载：重启 MCP 服务以刷新工具列表，并重新加载更新后的游戏桥接脚本（通常重载存档）。模组使用项目目录联接时无需另复制源文件。不要为了加载接口自动恢复已暂停的监控。
