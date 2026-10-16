# 接收器只读批处理

`read_batch(requests)` 将多项读取放入一次消息，在游戏接收器内顺序执行。需要桥接版本 0.12.22，并以心跳 `readBatchVersion=1` 判断实际加载能力。旧接收器会在发布请求前被拒绝，不自动回退成多次请求。

```json
{
  "requests": [
    {"command": "get_game_state", "arguments": {}},
    {"command": "list_towns", "arguments": {"limit": 20}},
    {"command": "get_town_overview", "arguments": {"town": 100}}
  ]
}
```

城市 100 仅为示例，应先读取当前地图的真实 ID。

## 支持的读取

- 游戏：`get_game_state`、`get_finances`、`get_map_info`。
- 列表：`list_towns`、`list_lines`、`list_vehicles`、`list_stations`、`list_depots`、`list_vehicle_models`。
- 详情：`get_entity`、`get_terrain`、`get_vehicle_motion`。
- 城市及产业：`get_town_overview`、`get_town_cargo_supply`、`get_industry_bonuses`。

参数遵循接收器命令的原有 schema；列表仅支持原始 limit、mine_only 等参数，不包含客户端额外过滤（例如 list_vehicles 的 line 参数）。未列出的命令、写入、预览、保存、读档、任意代码和嵌套批处理均拒绝。主机与接收器分别校验整批参数，任一参数非法时整批不执行。

## 返回与限制

最多 16 项，整个请求最多 8192 UTF-8 字节。`results` 保持输入顺序，每项包含从 0 开始的 `index`、`command`、`executed`、`ok`，及 `result` 或 `error`。

运行时单项异常不影响后续项。累计结果采用 48000 字节预算，超限项以 `response_size_limit` 代替，后续小项仍可执行；编码异常返回 `response_encoding_failed`。外层传输仍保留 65536 字节保护。

使用接收器现有 `os.clock` 时钟提供 100ms 软预算，仅在各项之间检查，不能中断单个原生调用，也不保证一帧内完成。超时后的未执行项返回 `time_budget_exceeded` 和 `executed=false`。时钟不可用时整批失败。`elapsedMs` 为该时钟下的执行耗时，不是客户端端到端延迟。

批级 `complete` 仅表示所有查询成功返回，不意味着子结果的业务数据完整。例如城市概览仍需检查自己的 `complete` 和逐字段 `available`。不将未知当零。

这不是并行执行或原子快照，也没有跨请求快照一致性保证。它复用单请求的会话、pending、回执与去重保护，不新增写操作或自动重试。原始扩展查询通道沿用内部 `build` 分类，这是传输分类，不代表允许批处理施工。

## 验证状态

已完成模拟原生 API 下的接收器分发、顺序、参数拒绝、单项异常、响应预算、时间预算与旧版本拒绝测试。2026-10-16 已确认新版接收器加载，完成5项基础查询和3城市概览批量读取；各项均成功且结束后无 pending。一次基础查询对照中，批量约0.94秒、逐项约4.96秒；这是单次样本，尚非稳定性能基准。减少的是消息往返与轮询开销，实际收益取决于每项查询耗时，不能替代游戏模拟等待。


## 规划默认入口（2026-10-16）

MCP `read_planning_data(requests)` 接受一个依赖轮次的1～256项独立查询。它使用同一白名单，预先校验整轮，然后按每批最多8项和8192字节依次调用接收器 `read_batch`；结果保留全局输入顺序，附带 `batchCount`、批次耗时及失败摘要。不会自动枚举全地图或补充用户未要求的查询。

例如首轮批量读资金、城市和必要设施列表；拿到真实城市ID后，第二轮批量读这些城市的需求和概览；确定目标后，第三轮读取候选实体。第二轮必须使用第一轮实际返回的ID，不能在一个批次中引用尚未返回的结果。

仅对已明确返回的 `time_budget_exceeded`（未执行）和 `response_size_limit`（已执行但未返回数据）重新组成单项批次，最多一次。单项仍超限就保留错误；成功项不重读，原生错误不重试，通信超时/错误及回执错配立即停止后续批次。大小限制后的再次读取是新样本，不保证与原批数据同一时刻。子查询业务完整性由调用者判断。

贴路选址 `RoadsidePlacement` 已接入：模板内部道路、候选道路详情和端点配置默认分组读取；仅复用本轮组件缓存，候选发现与后续详情仍分轮。障碍候选按最多8项的小组读取，发现不可行后停止扩展。地形检查后的条件查询、原生预览、资金刷新、提交和独立读回保持原有顺序。

已有 `get_planning_snapshot` / `get_route_snapshot` 本来就是一次请求的聚合读取，保持现有实现。历史 eval 调查脚本未被冒充成只读白名单，也没有自动迁移为批处理。新入口及贴路集成只需重启/重连 MCP Python 服务，接收器仍使用已验证的 `readBatchVersion=1`，无需为本次客户端调整重新加载地图。

规划入口实机验证：首轮3项基础查询一次返回，取得3座城市真实ID后，第二轮9项详情自动拆成8+1两批，约2.12秒全部返回，结束后 pending=null。证据见 `output/read_batch_20261016/live/planning.json`。贴路组件批量集成已完成离线测试，未进行本次实机施工验收。
