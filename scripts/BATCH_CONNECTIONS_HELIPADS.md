# 批量仓库接路与直升机设施

两个脚本均支持 `preview`、`build`、`verify`。预览不施工；build 必须游戏已暂停，先保存存档，实时解析实体并严格预览，再逐项单次提交、读回、保存。超时或部分成功写入记录并停止，禁止自动重发。

在项目根目录 PowerShell 执行：

```powershell
$env:TF3_MCP_DIR='D:/Program Files/Steam/userdata/1112836998/3493540/local/tf3_mcp'
server/.venv/Scripts/python.exe scripts/batch_connections.py preview
server/.venv/Scripts/python.exe scripts/batch_connections.py build
server/.venv/Scripts/python.exe scripts/batch_connections.py verify

server/.venv/Scripts/python.exe scripts/batch_helipads.py preview
server/.venv/Scripts/python.exe scripts/batch_helipads.py build
server/.venv/Scripts/python.exe scripts/batch_helipads.py verify
```

## 道路批次

`batch_connections.py` 针对当前四座大型仓库 W1–W4。使用调查过的公路节点坐标与入口前沿走廊；每次按坐标重新解析公共道路节点，不使用历史实体编号。道路为直线段，必要时通过折点绕开设施。保留仓库四模块占地与后方扩建空间；前侧为入口和道路通道，192×192 米扩建预留属于估算，未进行原生升级预览。

道路资源使用 `country/country_new_small`，地面道路，不自动切分旧边、架桥、挖隧道或拆除障碍。当前地图更换或公路锚点移动后必须重新调查并更新 `ANCHORS`。脚本不是任意地图通用选址器。

成功施工要求原生 `built`、`complete`、`verified` 全部为真，表示该次公共路口 CAR/TRUCK 双向连接通过。随后读回道路几何。verify 比对施工记录中的几何，不能证明当前寻路、仓库货运覆盖或长期模拟安全。道路被替换后停止重新调查，不重复建造。未知提交且没有完整读回记录时，verify 也会停止并要求按坐标核对真实地图。

仓库没有自带卡车终端；入口道路建成后，仍需要货运站真实覆盖、装卸配置和运输验收。道路记录位于 `exports/supply_warehouse_20261002/road_batch/ledger.json`。

## 直升机设施批次

`batch_helipads.py` 默认从优化方案读取 29 个陆地停机坪（16 城市、13 产业）。两处渔场岸边中转尚无明确陆地设施位置，排除施工。原生资源为 `::/stations/air/helipad.con`，1950 年起可用，36×38 米；保留 90×90 米用于第二停机坪及接驳的空间估算。入口道路 snap point 为局部 `(0,-25)`，需要另行规划道路。

磁盘桥接新增 `build_helipad` 和对应 MCP 包装。批量脚本在局部隔离 Lua 环境加载接口，无需重载游戏，也不写全局变量。预览与提交时的二次预览分别独立；提交调用内部重新预览并立即消费新令牌，不复用跨调用令牌。

可按编号选择，例如：

```powershell
server/.venv/Scripts/python.exe scripts/batch_helipads.py preview --ids H07 H19 H20 H21 --output exports/supply_warehouse_20261002/helipad_four
```

上述四处是徐州、锯木厂、砖厂、炼油厂。build/verify 必须使用相同 `--ids`、方案与输出目录。改变清单会拒绝旧 ledger，应另选输出目录。完整记录默认在 `exports/supply_warehouse_20261002/helipad_batch_all/ledger.json`。

施工后的设施验收读取当前资源、位置、朝向、所有者，以及原生车站货物装卸终端和 catchables。列出覆盖实体供后续核对；不把存在终端视为货源覆盖成功。脚本不创建线路或购买直升机，真实装卸和长期模拟仍待验收。

两脚本沿用仓库批次同一个桥接目录互斥锁和会话检查（城镇/产业坐标、玩家、世界、日期和 tick 回退）。存档加载或手动修改之后重新调查；锁不能阻止玩家手动操作，施工期间不要同时改动目标设施或道路。
