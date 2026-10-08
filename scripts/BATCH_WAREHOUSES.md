# 批量仓库脚本

`batch_warehouses.py` 默认读取徐州地图的 `exports/supply_warehouse_20261002/optimized_network.json`，处理其中4座仓库。不会自动建接驳道路、货站、线路或购买车辆；它们目前只有规划走廊，不能直接作为施工参数。

在项目目录执行：

```powershell
$env:TF3_MCP_DIR='D:/Program Files/Steam/userdata/1112836998/3493540/local/tf3_mcp'
server/.venv/Scripts/python.exe scripts/batch_warehouses.py preview
server/.venv/Scripts/python.exe scripts/batch_warehouses.py build
server/.venv/Scripts/python.exe scripts/batch_warehouses.py verify
```

- `preview`：只读检查地图、原生模板资源、地面、已有仓库及原生几何预览，不保存或施工。资源不可用、碰撞或结果不明确时停止。
- `build`：要求游戏已暂停；先保存独立施工前存档，每座重新检查原生模板资源、现场预览、单次提交、读回配置和库存、保存阶段存档。不会复用前一次preview令牌，不改变游戏速度。
- `verify`：只读重新定位仓库，检查位置、朝向、所有权、4模块布局、至少2000库容、目标货物支持及原生货站覆盖。实际道路寻路、线路、收发货、长期模拟和重载列为待验收，不假称仓库已通车。

输出默认在 `exports/supply_warehouse_20261002/batch/ledger.json`，可用 `--output` 指定目录；`--plan` 指定方案文件，`--bridge-dir` 指定桥接目录。施工过程中保留同一份ledger；不要换目录规避未知提交标记。

脚本在桥接目录持有进程级仓库批次锁，不允许另一个同类批次同时执行；进程退出会自动释放操作系统锁。此锁不禁止游戏内人工施工或其他MCP工具，批次期间仍需避免同时改图。

## 从零新建（桥接0.12.3）

脚本改用 `build_warehouse`，不再要求已建仓库模板。它核对当前年代的原生通用仓库元模板、入口脚本、模块类型和建造许可，按已核对的原生槽位编码生成布局：模块资源 `::/warehouses/wh_universal.module`，槽位坐标 `(0,3)、(4,3)、(0,7)、(4,7)`，每个500库容。原生工厂是定义 `data()` 的Lua脚本，不能直接require到全局；接口按原生资产复现初始化编码，保留资源metadata和updateScript，并走原生几何预览。

MCP新工具需刷新连接；普通脚本调用需游戏加载新版桥接。如果当前游戏仍使用旧版，可显式使用磁盘接口：

```powershell
server/.venv/Scripts/python.exe scripts/batch_warehouses.py preview --disk-bridge
server/.venv/Scripts/python.exe scripts/batch_warehouses.py build --disk-bridge
```

`--disk-bridge` 在每次现有eval调用内隔离加载磁盘桥接，不写 `_G`、不重载游戏、不替换GUI桥接。提交调用会重新原生预览，并在同一实例内消费新令牌；之前预览令牌不复用，结果附带 `freshPreview`。源码或输入改变则停止。实际引擎eval跨请求不能可靠保留scratch，因此不使用跨请求保存的实例/令牌。只读 `check_warehouse_interface.py` 也可验证当前方案的4座原生预览，不提交。

预留16模块只用于保护扩建空间，脚本初期仅复制4模块，不自动扩到8000库容。192×192米预留来自原生模块尺寸估算，并非升级原生预览。

## 故障与重复执行

每次提交前先原子写入 `commit_started`。超时、部分成功、验收失败进入 `needs_reconciliation`，后续build直接停止。先运行verify读回实际地图；已找到且静态验收通过时可核实为 `static_verified`，未找到则保留人工核对要求，禁止自动重发。配置不匹配的已有仓库也会停止，不覆盖或重复建设。

已匹配的仓库再次运行会跳过施工并重新验收。地图指纹按城镇名称、产业资源和坐标比对，实体ID每次重新解析；施工中检测时钟/tick回退及模板改变。相同地图的重载仍可能无法仅凭指纹识别，因此不要在批次中手动重载或同时施工。桥接自身进一步检查令牌时效和源布局。

保存回调为空函数，不写全局；文件大小稳定只证明文件写出，不能证明存档重载或长期模拟安全。首次未验证布局仍应遵循项目手册，在隔离测试存档验证。

离线测试：

```powershell
server/.venv/Scripts/python.exe -m pytest scripts/tests/test_batch_warehouses.py -q
```
