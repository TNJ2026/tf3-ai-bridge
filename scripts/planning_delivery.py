"""Current-state documentation generated from the same plan as execution."""
import hashlib
import json
from fullmap_workflow import atomic_write, write_json


def write_delivery(output, plan):
    digest = hashlib.sha256((output/'network_plan.json').read_bytes()).hexdigest()
    gates_path = output/'acceptance_gates.json'
    gates = json.loads(gates_path.read_text('utf8')) if gates_path.exists() else {}
    existing = [f['id'] for f in plan['facilities'] if f.get('reuseOnly')]
    ops = plan.get('operations_review', {})
    detailed = ops.get('mode') == 'detailed'
    pending = [r for r in ops.get('chains', []) if r['riskForecast']]
    tables = []
    for r in ops.get('chains', []):
        def number(x): return '?' if x is None else f'{x:.1f}'
        tables.append(f"| {r['route']} | {number(r['travelSeconds'])} | {number(r['estimatedTotalSeconds'])} | {number(r['deadlineSeconds'])} | {r['riskForecast']} |")
    operations = ('# 运营规划检查\n\n'+(
        '本次采用基础模式：只记录维护候选和终端分配，不推算往返时间、班次、全链时效或平台占用。未知数据不触发补采或容量复核。\n\n'
        if not detailed else '本次已显式启用详细运营预测，仅作优化参考，未知数据不触发补采或验收。\n\n')+
        '## 维护基地\n\n'+ '\n'.join(f'- {k}：计划服务 {v:g} 架飞机。' for k,v in ops.get('maintenance',{}).get('fleetLoadByBase',{}).items())+'\n\n'+
        '维护能力、真实终端与必要库存覆盖在对应建设阶段读回。载具只验实际驶离基地、正常执行线路及无原生故障。\n')
    if detailed:
        operations += '\n'+(
        '以下均为离线预测；维护能力与真实终端在相应施工阶段核对，货物计时和排队未知不增加常规试车。预算按当前任务授权执行。\n\n'+
        '优先线路两端机场；按预计机队负荷分配。端点无候选时才比较附近机场。维护需求不计入当地货物吞吐。\n\n'+
        '## 全链时效\n\n串联运输段累计行程与半个发车间隔；并行线路按货量加权，不能串联相加。缺少数据标为未知，不阻塞投运验收。期限优先采用货物本身配置，缺失时取相关线路最严格值；换乘计时规则未原生验证，不作为实际超时判定。\n\n'+
        '| 货流 | 行程秒 | 含等待估算秒 | 期限秒 | 风险估计 |\n| --- | --- | --- | --- | --- |\n'+'\n'.join(tables)+'\n\n'+
        '## 平台占用\n\n'+ '\n'.join(f"- {r['facility']} / 终端 {r['terminal']}：{len(r['lines'])} 条线，占用估算 {r['occupancyEstimate']:.1%}，容量优化提示={r['capacityReviewRequired']}。" if r['occupancyEstimate'] is not None else f"- {r['facility']}：缺少班次数据，估算未知。" for r in ops.get('platforms',[]))+
        '\n\n占用率采用每次停坪 60 秒的假设，仅用于排序；未计入维护占用，不作为常规投运门槛。每坪三线仍是既有规划上限；不为精算占用额外试运行。\n')
    else:
        operations += '\n## 终端分配\n\n'+ '\n'.join(
            f"- {r['facility']} / 终端 {r['terminal'] if r['terminal'] is not None else '待绑定'}：{len(r['lines'])} 条线。"+
            ('超过既有每坪三线规划上限，需调整分配。' if r['capacityReviewRequired'] else '')
            for r in ops.get('platforms',[]))+'\n'
    atomic_write(output/'OPERATIONS.md', operations)
    atomic_write(output/'EXECUTION.md', '''# 批量执行与分阶段验收

所有命令必须显式指定当前 plan/output；文档和预测不构成游戏操作授权。集合、线路、车辆分别按用户授权执行，当前交付包不自动开启提交。

1. **离线准备**：运行 `scripts/plan_finalize.py --pack <目录>`，再运行 `scripts/plan_finalize.py --pack <目录> --check`。检查计划摘要、线路/车辆对应关系和编译集合。阅读 OPERATIONS.md；全链时效及平台占用是估算，不能据此声明运营通过。
2. **建前门槛**：确认当前会话、存档备份和暂停状态，重新解析实体。已有 HQ 按 reuseOnly 只读复用，使用 `scripts/hq_existing_access.py`；不存在或发生移动须停批，不补建。编译规格不是可复用的原生预览。
3. **集合预览**：公共入口为 `scripts/build_joint_collection.py preview --plan <network_plan.json> --output <执行目录> --owner <集合> --compiled-dir <compiled_groups>`。测试环境或当前地图测试标志仅在取得对应授权后使用。规格含设施、组内道路和外接道路；按位置重新解析外部节点，检查碰撞、双向货车通路和机场道路链接。不要运行旧的本轮专用 preview_groups.py。
4. **单次施工**：对应 build 操作使用同一编译器和完整规格。批量集合入口 `scripts/construct_planned_map.py --plan <计划> --output <执行目录> --compiled-dir <compiled_groups> --owners <逗号列表> --authorize-build`，另按已获授权传入测试环境标志。每组提交前持久化意图，提交后独立验收。已由集合消费的道路不可再独立施工。未知结果、超时或部分成功停批，不重发。
5. **建后门槛**：设施和道路数量、模块、实际入口、外接道路双向路径、机场道路链接、真实主仓库库存和维护均须读回。城市集合另验客站—机场换乘；四设施生产集合不套用该项。共库采用 primary_warehouse 公共检查，不要求客站、车库或维护设施覆盖货物库存。建后证据尚不存在时标 pending，不能提前标通过。
6. **捕鱼集合**：按当前模板执行联合岸线预览与单次提交；共库检查和航路分别验收。常规不执行往返航路查询；显式故障诊断时才运行 `scripts/ship_route_checks.py --plan <计划> --output <新结果.json> --readback --diagnose-round-trip`。船型兼容和维护设施能力仍保留。见公共船舶指南。
7. **线路与车辆门槛**：基础设施通过后才绑定真实 station/terminal，显式源装目的卸。车辆入口为 `scripts/fullmap_fleet.py preview|build|verify --plan <计划> --output <执行目录> --fleet <fleet_manifest.json>`，支持逐线车型、数量和指定采购基地；每辆单独记账、提交、读回，部分采购不重发。旧 fullmap_vehicles.py 拒绝现代计划。维护基地分配目前为规划候选，尚未验证或自动应用维护指令。
8. **运营门槛**：所有载具只确认实际驶离基地、正常执行所配线路且无原生线路故障；不额外测试返程、回库或完整往返，公交/货车不验证上下客或交付数量。自动检查点采用同图固定槽，并确认文件更新。静态配置不能代替实际驶离基地；确认后即可结束观察，未观察的长期目标不声明达标。账户监控保持暂停，现金底线150万元。

代码新增路径已做离线验证，当前版本仍需取得授权后的代表性原生预览与验收。禁止把建后门槛改成已通过来放行整图。
''')
    blockers = gates.get('blockers', [])
    atomic_write(output/'BLOCKERS.md', '# 当前验收门槛\n\n'+
        '门槛按阶段处理；需要施工后才能取得的证据保留待验，不构成建前死循环，也不授予施工权限。\n\n'+
        '\n'.join('- **'+b['id']+'**：'+b['reason'] for b in blockers)+'\n\n'+
        '\n'.join('- 待办 **'+b['id']+'**：'+b['reason'] for b in gates.get('pending',[]))+'\n\n'+
        (f'专项预测中 {len(pending)} 条货流有已估算的时效风险；未知数据不列作待办。详见 OPERATIONS.md。\n\n' if detailed else '基础模式未计算时效或平台占用，不因缺少这些数据增加待办。维护基地须在对应执行阶段确认能力与通达。\n\n')+
        '总部现状以 network_plan.json 的 reuseOnly 与入口证据为准；已验证的真实自动链接和双向连接图，不等于未通过的跨链接原生路径查询或扩建预留已解决。\n')
    atomic_write(output/'DELIVERY.md', '# '+next((c['name'] for c in plan['cities'] if c['id']==plan['focus_town']),'当前主城')+'主城 · 全图货运规划交付\n\n'+
        f"当前离线规划包登记：{len(plan['cities'])} 个城市、{len(plan['industries'])} 个生产设施；{len(plan['hubs'])} 个陆上集合、{len(plan.get('ports',[]))} 个捕鱼集合、{len(plan['line_specs'])} 条货运线路。这些数量不是当前地图实况，也不表示现场施工或投运已经验收。\n\n"+
        ('已登记复用设施：'+ '、'.join(existing)+'。执行前须重新解析和只读验收。\n\n' if existing else '本计划未登记已建复用设施；当前地图仍须现场确认。\n\n')+
        '[运营预测](OPERATIONS.md) · [执行步骤](EXECUTION.md) · [待验门槛](BLOCKERS.md) · [供需边界](SUPPLY.md) · [设施清单](FACILITIES.csv) · [线路清单](LINES.csv)\n\n'+
        'network_plan.json 是计划源；清单、图表和编译规格须匹配其摘要。历史原生预览只作证据，当前会话需要重新预览。本轮代码与文档更新不操作游戏，也不恢复监控。\n\n'+
        '覆盖全部服务对象不等于满足全部需求。资源种类齐全时，产能不足不能触发资源勘探。\n\n'+
        'report_plan.json 为当前离线图表输入；report/ 内既有渲染文件属于历史快照，不作为本版执行依据。需要展示最终卡片时再按公共流程导出。\n')
    outputs = ['FACILITIES.csv','LINES.csv','report_plan.json','DELIVERY.md','EXECUTION.md','BLOCKERS.md','OPERATIONS.md']
    write_json(output/'delivery_integrity.json',dict(planDigest=digest,
        artifacts={f:hashlib.sha256((output/f).read_bytes()).hexdigest() for f in outputs},gameCalls=0))
