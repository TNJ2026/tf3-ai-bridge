# 停机坪批量接路

```powershell
$env:TF3_MCP_DIR='D:/Program Files/Steam/userdata/1112836998/3493540/local/tf3_mcp'
server/.venv/Scripts/python.exe scripts/batch_helipad_roads.py preview
server/.venv/Scripts/python.exe scripts/batch_helipad_roads.py build
server/.venv/Scripts/python.exe scripts/batch_helipad_roads.py verify
```

从当前地图重新解析 29 个停机坪的完整平面朝向。读取公共道路节点，优先无显式转向配置的节点或只有空转向配置的道路末端，避开已记录为不通的锯木厂仓库支路。原生入口位于局部 `(0,-25)`；前沿道路中心放在局部 `y=-35`，避开设施碰撞。路径保留前侧接驳及后侧扩建空间，扩建余量为估算。

按长度排序，比较直线、折线及曲线采样候选；必要时按旧道路真实切线延伸后绕行。原生预览拒绝未知碰撞、错误或阻挡。只新建地面道路，不切分既有道路，不拆建筑，不覆盖自定义转向配置，不忽略错误。

build 要求地图已暂停，保存独立基线并逐项单次提交。提交结果必须同时 `built/complete/verified=true`；读回道路实体，并通过原生 `TP_NET_LINK` 核对道路与停机坪的真实自动连接。公共接入点的 CAR/TRUCK 双向路径由现有道路接口验证。设施入口不是卡车终端；连通不等于货源覆盖、线路运行或实际送货。

超时、部分成功、实体改变或设施链接未确认时停止，记录 `needs_reconciliation`，禁止重新提交。没有安全候选的项目记录 `no_safe_route`，不施工，继续处理其他独立设施。重复执行会验收已完成项目，不重建。记录位置为 `exports/supply_warehouse_20261002/helipad_roads/ledger.json`，包含输入、候选预览、单次提交、原生链接、存档和未完成事项。

当前地图名称、产业位置和玩家与原方案一致才允许执行。图形仅用于候选比较，真正建造使用实时原生预览。长期模拟和重载验证另行进行。
