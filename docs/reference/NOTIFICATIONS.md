# 原生通知读取

`get_notifications(include_history=False, offset=0, limit=100)` 为只读接口，要求当前接收器心跳与原生能力中 `notificationsVersion=1`。旧接收器在请求发布前拒绝，不尝试未知命令，不清 pending。

## 范围与口径

- 默认返回原生通知栏候选：ID 位于 `NotificationsState.history` 且 `dismissed` 不为真。按时间、ID 升序，与 `notification_popups.tl` 的列表选择和排序一致。
- `include_history=True` 返回 `notifications` 中所有保留条目，包括关闭、过期、未跟踪及不在 history 的条目；不是无限历史。`inHistory`、`tracked`、`expired`、`dismissed` 分开返回。
- 不额外按超时时长、过期标记、忽略类型重新推算当前列表；这些更新归原生模拟负责。缺少布尔字段按原生列表的 nil 语义处理，同时用 `*Recorded` 标明是否原生实际记录。
- `popupEligible` 不是像素可见性。原生 React 可因正文状态未就绪不渲染图标，UI 还有布局、悬浮和过场状态；`screenVisibleKnown=False` 明确说明未读取这些界面状态。接口不声称知道当前悬浮展开的是哪条。
- `historyComplete=False` 与 `missingHistoryIds` 表明原生列表引用缺失；整个脚本或 history 不可用时显式失败，不返回伪空列表。
- `offset` 从0开始，`limit` 1～100（主机通道上限）。分页为实时读取，模拟推进时结果可能变化，应核对 `gameTime`，需要一致批次时使用足够大的单页。返回 `total/currentCount/hasMore/nextOffset`。

## 返回内容

每条保留原生表键 `id`（不误用载荷内 notificationId）、时间、类型、资源分类、原始 `params/simParams/persisting`、关闭/过期/跟踪状态和机遇 UID。实体及版本引用保留在原始参数中，不把任意整数猜作实体。资源分类无法取得时为 Unknown。原始载荷使用现有桥接有界序列化，不保证任意第三方超大载荷无截断。

正文与列表成员资格独立：

- 城镇严重评分警报、新产业通知：按已核对原生模板及其缓存名称、评分标签格式化；翻译由原生 `_` 与 `lang_util.format` 完成。
- 货物供应产业和连接城镇机遇：调用白名单中原生 `getNotificationData` 只读格式化函数，校验资源到 `.script@入口` 的间接映射；不调用接取、模拟更新或卡片操作。
- 其他通知或缺少原生名称、simParams、渲染依赖：条目继续返回，`textKnown=False` 和 `textUnavailableReason` 说明原因。不得把分类名称冒充通知正文。

没有执行 `useDataState`/React hooks，没有 GUI 点击、关闭、标记已读、模拟更新、事件提交、随机数调用或机遇接取。

## 验证与生效

2026-10-13：130项通知及相关通道/机遇/勘探/产业加成回归测试通过；Lua 5.1～5.5、LuaJIT 加保留局部变量余量的编译检查通过。测试覆盖原生筛选和排序、历史分页、缺失引用、未知文本、原生格式化入口校验、只读约束、MCP路由及旧接收器发布前保护。

**当前地图实机读取已通过。** 用户手动加载后，原生能力 notificationsVersion=1；读取当前3条通知，全部中文正文解析成功，保留历史38条，前两页分页通过且游戏时间一致。未点击、关闭、接取或改速，未重新进行屏幕像素/悬浮对照。首次limit1024主机发送前拒绝已改用通道上限100，并补正边界测试。详见 `output/notifications_api_20261013/RESULT.md` 和 `live_result.json`。安装备份记录为 `deployment.json`；常驻MCP服务仍需加载新版Python才能在工具列表中显示新工具。
