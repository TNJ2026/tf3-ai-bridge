# 原生界面与诊断接口（nativeExtrasVersion=1）

> 用户范围调整（2026-10-17）：声音效果，标记、高亮、驾驶舱等视觉效果及过场动画暂时忽略，不再作为本轮完成条件，不继续效果验收，也不记为通过。已有回执与未确认状态保留，详见[验证台账](../../output/api_all_20261017/RESULT.md)。

> 全目录验证台账（2026-10-17）：补测镜头聚焦/跟随/驾驶舱、界面高亮与引导、HUD、音效/语音和截图。跟随有相机读回，引导shown=true；像素/音频效果仍未确认，截图尚未发现新文件。标记类型与过场资源未确认，两类效果未执行，不把依赖可用性作为全部验收。见[完整台账](../../output/api_all_20261017/RESULT.md)。

> 新增车辆现场验证：线路18869的终端建议查询通过，未应用；车辆18502的路径显示及移除原生调用通过，未进行像素验收。见[车辆与线路测试](../../output/api_vehicle_tests_20261017/RESULT.md)。

> 最新实机结果（2026-10-17，v0.12.67）：30项扩展能力、47项世界动作原生入口全部识别；世界动作保留39项开放/8项阻断。镜头、过场、性能、列车阻塞及环境采样只读调用通过，语音播放状态可读、空资源保留缺失标记。接收器ready、pending为空。GUI效果及世界写操作未执行，不能扩展为全部接口效果验收。见[逐项实机记录](../../output/api_live_v67_20261017/RESULT.md)。

> 最新状态：v0.12.66 实机已验证世界操作模块可加载并返回47项目录，接收器保持 ready、无pending。诊断确认原生函数实际为table，旧函数类型检查误报不可用；v0.12.67 / revision43 已改用项目既有原生绑定兼容检查，213项专项与编译/包校验通过，等待再次载入地图验收。见[复验记录](../../output/api_live_v66_20261017/RESULT.md)。

> 修复进展：0.12.66 / revision 42 已部署，完整资源路径、固定原生 API 引用及预检错误回执已修复；离线回归/编译/包校验通过，等待重新载入地图验收。原失败请求已按固定源码和日志证据记录为引擎分发前拒绝，未重发。见[修复记录](../../output/api_fix_20261017_211817/RESULT.md)。

> 2026-10-17 实机验证未通过：能力查询返回29项不可用；世界动作目录因模块加载失败使接收器停止。仅连接、地图身份及能力目录读取通过，未进行世界写入。详见[实机验证记录](../../output/api_live_20261017/RESULT.md)。以下离线实现/部署状态不代表实机可用。

本页封装范围是讨论中的九类非属性能力：镜头、地图标记、界面引导、声音/过场、性能、列车阻塞、终端建议、目的地市民和环境采样。共30个具名MCP工具，不是任意API代理。随后补充的产业倍率、日期、库存等写入入口见[世界操作接口](WORLD_ACTIONS.md)，其阻断项与实现边界单独记录。

状态：2026-10-17 已部署到本地 staging（0.12.65 / revision 41），离线包校验和六种 Lua 运行时编译通过；MCP 新进程导入注册通过，现有进程尚未重连。游戏心跳过期，原生模组校验及游戏重载后的接口验收仍待完成。接口存在不等于某个地图/场景支持其全部效果。读取`get_native_extras_capabilities`检查逐工具依赖；`available`只表示函数存在，不表示已完成实机验收。

## 工具目录

| 类别 | MCP工具 | 官方入口（api下） |
|---|---|---|
| 能力检测 | `get_native_extras_capabilities` | 按白名单逐项检查函数 |
| 镜头 | `focus_game_entity`, `focus_game_position` | `gui.camera.focusEntity`, `focusPosition` |
| 跟随/驾驶舱 | `follow_game_entity`, `enter_vehicle_cockpit`, `leave_vehicle_cockpit` | `gui.camera.followEntity`, `enterFollowCameraCockpit`, `leaveFollowCameraCockpit` |
| 截图/镜头读取 | `take_game_screenshot`, `get_game_camera` | `gui.camera.takeScreenshot`, `getEye`, `getCenter`, `getFollowEntity` |
| 地图标记 | `set_map_marker`, `remove_map_marker` | `gui.mission.setMarkerAtPosition`, `removeMarker` |
| 圆形范围 | `set_map_circle`, `remove_map_circle` | `gui.mission.setZoneCircle`, `removeZone` |
| 路径展示 | `show_vehicle_path`, `remove_vehicle_path` | `gui.mission.setMovePathVisualizationAtEntity`, `removeMovePathVisualization` |
| 高亮/引导 | `highlight_game_ui`, `show_game_guide`, `reset_game_guide` | `gui.byId.setHighlighted`, `gui.guide.trySpawnGuideById`, `resetGuide` |
| 临时图标 | `show_entity_hud_icon` | `gui.spawnEphemeralHudImage` |
| 鸣笛/音效 | `sound_vehicle_horn`, `play_game_sound` | `gui.sound.letVehicleHorn`, `playRandomSoundEffect` |
| 语音 | `play_game_voiceover`, `stop_game_voiceover`, `get_game_voiceover` | `gui.voiceOverManager.play`, `stop`, `isPlayingAny`, `getPlaying` |
| 过场 | `play_game_cutscene`, `get_game_cutscene` | `gui.mission.playCutscene`, `isCutscenePlaying`, `getCutsceneElapsedTime` |
| 性能 | `get_game_performance` | `gui.benchMark`的8种计时序列 |
| 阻塞列车 | `get_blocked_trains` | `engine.system.landVehicleMoveSystem.getBlockedTrains` |
| 终端建议 | `get_line_terminal_suggestions` | `engine.system.lineSystem.getBestLineAssignment` |
| 目的地市民 | `get_destination_persons` | `engine.system.simPersonSystem.getSimPersonsForDestination` |
| 环境采样 | `sample_environment` | `engine.system.emissionGridSystem.getInterpolatedEmission` |

## 执行和返回语义

- GUI功能在GUI回调中执行，不发送到引擎执行，也不伪装成工程。四项运输/环境诊断通过现有引擎事件通道读取。
- 主机保留会话绑定、公共锁、持久请求账本和pending保护；旧接收器缺少`nativeExtrasVersion=1`时，在发布请求前拒绝。接收器仍双重检查参数和请求ID。
- GUI效果每会话最多256次，效果请求ID不在读请求轮转时淘汰；达到限制拒绝后续效果，不自动重载或重发。GUI只读查询可轮转；引擎只读查询不计施工额度。
- `requested=true`表示原生调用返回；`visualVerified=false`不承诺用户已经看见/听见。截图不返回图像字节、不猜保存路径，`fileVerified=false`。过场播放不代表已完成。
- 标记、圆圈、路径的key统一加`tnj_mcp_extras_`前缀，删除只影响该命名空间。同一key可更新。圆圈强制`prohibitBuilding=false`；它是示意范围，不证明真实服务覆盖。`marker_type`须提供已知原生类型，不硬编码未经验证的默认值。
- 高亮只匹配明确UI ID（`idOnly=true`），`highlighted=false`清除。引导保留原生`shown=false`，不报成功显示。`reset_game_guide`和停止语音可能影响游戏或其他脚本打开的引导/语音。
- 图标、音效、语音和过场只接受显式游戏资源URI（例如`::/…`或`mod_id::/…`），拒绝操作系统路径、反斜杠和路径穿越。仅URI语法校验，不证明资源存在；使用前从已加载内容确定真实资源。
- 暂无原生过场停止接口封装；不要用未验证事件名补造停止能力。退出驾驶舱不等于退出全部跟随模式，可使用定位位置接管镜头。
- 分字段读取返回`available`/`complete`，缺失和异常不当零。性能样本保持原生顺序和未明确单位，不冒充毫秒或FPS；`guiUpdate`来自`getCoreStepTimes`，`simulation`来自`getGameStepTimes`。
- 阻塞列车保留原生二元组`first/second`，官方本机注释未说明方向，不擅自认定谁阻挡谁。
- 终端建议使用当前LINE组件，返回0基站点、station/terminal索引；`applied=false`，不改线路、不代表已解决冲突。
- 目的地市民是以实体为住宅、工作或购物目的地的人，不等于当前正在前往或候车人数。按ID排序分页；`snapshot=false`，模拟运行时分页可能变化。
- 环境值是原生排放网格读数，不是模型0～100评分。支持当前/平均口径；噪音、污染分别报告可用性。

## 边界和验证

每页/序列最多200项，原生列表最多检查200000项，超过或结构不可读明确失败；终端建议最多128站。坐标、颜色、缩放、距离和持续时间具有有限范围校验；这些是适配器限制，不是游戏最大值。请求上限4096字节，双方及心跳保持一致。未知结果检查原请求，不自动重试。

离线测试覆盖全部30个工具的GUI/引擎分流、MCP参数默认值、非法输入、旧接收器拒绝、原生函数缺失、部分数据、重复请求、命名空间和不禁建等。使用真实桥接Lua和原生API模拟对象；尚未进行像素/音频效果或长期运行验收。

2026-10-17 验证结果：新增专项107项通过，相关通道回归240项通过，全量`server/tests`共2080项通过（91.80秒）。全量测试需将`server/src`与`scripts`加入`PYTHONPATH`。实际MCP `list_tools()`确认30个入口全部注册。源码差异空白检查通过。

参考：[官方GUI接口](https://wiki.transportfever3.com/script-doc/api/gui.html)、[官方引擎系统接口](https://wiki.transportfever3.com/script-doc/api/engine/system.html)。优先以本机游戏附带的`api/tealdef/api/`声明核对签名。
