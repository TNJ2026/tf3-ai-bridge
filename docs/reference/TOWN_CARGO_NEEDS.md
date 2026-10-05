# 城市货物需求编辑接口

编辑住宅、商业、工业的需求**货物种类**，不直接设置年度需求数量。使用原生 `api.cmd.makeTownUpdateCargoNeedsCmd(town, cargoNeeds, updateTownBuildings)`，由引擎执行；没有直接改写组件或游戏全局状态。

## 调用流程

1. 确认当前地图和城市实体，调用 `get_town_cargo_needs(town)` 读取当前三类需求。
2. 调用 `preview_town_cargo_needs(town, residential?, commercial?, industrial?, update_buildings=False)`。
3. 保存施工前独立存档；有本次需求修改授权后，在 60 秒内调用 `commit_town_cargo_needs(preview_token)` 一次。
4. 调用 `get_town_cargo_operation(operation_id)`，并再次 `get_town_cargo_needs(town)` 独立核对。

参数使用当前货品目录的原生整数 ID，不是 Lua 下标。ID 0（旅客）不属于本接口允许的货物；负数、未知 ID、重复 ID、非整数均拒绝。三个分区至少指定一个；省略分区保留原值；指定分区必须保持原有货品项数，只能等量替换，不允许新增或减少。原分区非空时 `[]` 被拒绝。完整列表替换该分区，不是追加。用货品目录解析 ID，不照搬历史地图编号。

例如仅修改商业需求，保留住宅和工业：

```python
current = await get_town_cargo_needs(town=current_town)
preview = await preview_town_cargo_needs(
    town=current_town,
    commercial=[current_food_cargo_id, current_clothes_cargo_id],
    update_buildings=False,
)
# 先保留独立备份，且已获得当前需求修改授权。
result = await commit_town_cargo_needs(preview_token=preview["preview_token"])
audit = await get_town_cargo_operation(operation_id=result["operation_id"])
```

## 结果和限制

- 预览只做参数、城市身份和当前需求检查，不发送原生命令，不等于原生建设预览或长期模拟验证。
- 提交前复核世界、玩家、城市实体 revision、游戏时间及原需求；目标已变或预览过期时拒绝。
- 令牌在发送前消耗。相同需求返回 `no_change=true`，不发送命令。
- 回调接受不等于成功；`verified` 只表示城市需求列表读回与目标一致，不表示现有建筑容量/需求量已全部刷新。
- `update_buildings=False` 默认不要求立即更新全部建筑；`True` 使用原生立即更新参数，可能同时更新建筑目标容量，不能描述为只改变显示文本。
- 超时、失败或读回未一致返回 `needs_reconciliation`；同一城市后续提交被阻止。通过 operation 查询或当前地图读回对账，不自动重发。Lua `pcall` 不能防护原生断言。
- 令牌和操作记录仅保存在当前加载的桥接状态。重载后失效，须保存调用结果作为外部账本，重新读取城市需求核对，不能直接重试旧操作。
- 2026-10-05 已在用户授权的当前测试地图完成鹤岗修改：商业仅鱼、工业仅砖石；单次原生提交、独立城市读回及建筑需求汇总通过。记录：`exports/hegang_demand_edit_20261005/RESULT.json`。重载持久性、城市升级后是否覆盖需求及长期模拟安全尚未验证。
- 原生 TOWN.cargoNeeds 是三层“货物 ID、权重”对；读取返回 `needs`（ID 列表）和 `weighted_needs`（原始权重），提交使用原生命令要求的 ID 列表。原生命令更新会递增城市 revision；成功同步读回绑定更新后的 revision，不能把正常更新误判为换图。
- Python MCP 和游戏桥接都须加载更新后的代码；刷新/重启 MCP 服务并按项目正常部署流程加载桥接。本次代码变更不会自动部署脚本或重载当前存档。

2026-10-05 用户修订：需求只能等量替换，不能减少；此前鹤岗删减操作已撤销，鱼/罐头与砖石/家具各两项及原权重已恢复。恢复记录：`exports/hegang_demand_restore_20261005/RESULT.json`。后续须先验证替代货品的完整供给链，再替换。

2026-10-05 后续实测：原生接口按货品重算权重，并不保留替换位置的原权重。鹤岗等量替换为商业衣物/罐头食品、工业机器/家具，四项权重均为 0.5；原鱼/砖石为 1。该接口不能保证年度需求总量不降低，也不能通过当前参数自定义权重。四项建筑年度需求独立读回通过，记录见 `exports/hegang_finished_goods_20261005/RESULT.json`。工厂存在不等于已接通供应。
