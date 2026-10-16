# 货运装卸语义与示例（2026-10-16）

`loads` 是**当前停靠项**的装载／保留货品列表，不是整条线路的“允许运输货品”清单。将同一货品列入每个站的 `loads`，可能使全线没有该货品的卸货站，触发装卸配置冲突。

| 停靠项用途 | 对目标货品的配置 |
|---|---|
| 生产源装货 | `loads: [cargoId]` |
| 目的站卸货，且不装其他货品 | `loads: []`，保留 `force_unload: false` |
| 仅途经、需要保留该货品 | 将该货品保留在 `loads`，不把此站算作卸货站 |
| 多货品或中转 | 逐站逐货品确定装载、保留或卸货，不复制同一列表到全线 |

`loads: []` 与省略 `loads` 不同：使用 `source_index` 时，省略会保留旧配置。目的站仍须有兼容的卸货终端及真实接收库存／城市覆盖。`force_unload: false` 不是禁止卸货，而是正常按接收容量卸货；不要用强制卸货绕过满库存或配置问题。

两站罐头线的编辑示例（Python 请求对象；`current_line_id` 必须为现场核实的整数 ID，货品28也须按当前地图确认）：

```python
request = {
    "line": current_line_id,
    "stops": [
        {"source_index": 0, "loads": [28], "force_unload": False},
        {"source_index": 1, "loads": [], "force_unload": False},
    ],
}
```

`source_index` 为零起始站序。接口 `loads` 使用真实货品 ID，不加1；原生 Lua 数组读回才用 `cargoId + 1`。

提交前逐站核对用途，走新鲜预览、单次提交和独立 `LINE` 读回。预览成功只证明配置可提交，不证明业务装卸正确。随后检查原生线路告警和车辆运行：`noPath=false` 不能替代装卸告警检查。存在未解析的 `lineIssues` 时保留原始参数并定向诊断，不按数字猜含义，也不因车辆已出库而忽略。

潮州实测：31279及四条原料线原先全站装载同一货品，通知含 `lineIssues=[[1,0,cargoId]]`。改为源头装载、目的站空列表后，五条线路告警消失；未改道路、未购车、未使用强制卸货。此证据不等于城市已收货或合同已完成。见[修复记录](../../output/chaozhou_start_20261016/monitor/CANNED_RESULT.md)及[单次提交与独立读回](../../output/chaozhou_start_20261016/monitor/canned_unload_repair_continued.json)。
