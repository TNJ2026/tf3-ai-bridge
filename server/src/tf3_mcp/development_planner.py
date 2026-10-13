"""Offline regional and site planning. Outputs are proposals, never build approvals."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .localization import language, translate as tr_text
from .route_planner import Terrain
from .staged_planner import detour, segment_points


def number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'{name} must be a finite number >= {minimum}')
    return value


def box(value):
    for axis in ('x', 'y'):
        lo = number(value['min'][axis], 'bounds minimum', -1e9)
        hi = number(value['max'][axis], 'bounds maximum', -1e9)
        if hi <= lo:
            raise ValueError('bounds must have positive area')
    return value


def overlaps(a, b):
    return all(a['min'][k] < b['max'][k] and a['max'][k] > b['min'][k] for k in ('x', 'y'))


def contains(a, b):
    return all(a['min'][k] <= b['min'][k] <= b['max'][k] <= a['max'][k] for k in ('x', 'y'))


def grid_bounds(g):
    return dict(min=dict(x=g['x'], y=g['y']), max=dict(x=g['x']+(g['nx']-1)*g['spacing'], y=g['y']+(g['ny']-1)*g['spacing']))


def validate_snapshot(s):
    g = s['grid']
    number(g['spacing'], 'spacing', 1)
    for k in ('nx', 'ny'):
        if not isinstance(g[k], int) or not 2 <= g[k] <= 100000:
            raise ValueError('grid dimensions must be integers >= 2')
    n = g['nx']*g['ny']
    if n > 100000 or len(g['heights']) != n or len(g['water']) != n:
        raise ValueError('incomplete or oversized terrain grid')
    box(grid_bounds(g))
    for h in g['heights']:
        number(h, 'height', -1e9)
    for row in s.get('obstacles', []):
        # Zero-width native boxes are allowed; no inference that they are clear.
        for k in ('min', 'max'):
            for axis in ('x', 'y'):
                number(row[k][axis], 'obstacle coordinate', -1e9)
    return s


def save_json(value, directory, stem):
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{stem}-{uuid.uuid4().hex[:12]}.json'
    tmp = path.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return str(path)


def read_snapshot(path):
    return validate_snapshot(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def supply_balance(chains):
    """Caller supplies measured or forecast finished-product equivalents in one time unit."""
    result = []
    names = set()
    for c in chains:
        name = str(c['name'])
        if name in names:
            raise ValueError('supply chain names must be unique')
        names.add(name)
        if not c.get('time_unit') or not c.get('cargo') or c.get('evidence') not in ('measured', 'forecast'):
            raise ValueError('supply chain requires cargo, time_unit and measured/forecast evidence')
        rates = {k: number(c[k], k) for k in ('demand', 'production', 'transport', 'handling', 'delivery')}
        # All shared-city demand must be summed by the caller. Unknown is never zero.
        capacity = min(rates.values())
        batch = number(c['batch'], 'batch')
        delay = number(c['delay'], 'delay')
        storage = number(c['storage'], 'storage')
        target = batch + rates['demand'] * delay
        result.append(dict(**copy.deepcopy(c), effectiveDelivery=capacity,
                           unmetDemand=max(0, rates['demand']-capacity),
                           bottlenecks=[k for k, v in rates.items() if v == capacity],
                           bufferTarget=target, storageGap=max(0, target-storage),
                           bufferModel='conservative batch + demand * delay; not a throughput increase',
                           supplyUtilization=None if rates['demand']==0 else capacity/rates['demand']))
    return result


def base_plan(snapshot, title, scope, chains):
    validate_snapshot(snapshot)
    return dict(schema=1, language=language(), title=title, scope=scope, createdAt=datetime.now(timezone.utc).isoformat(),
                snapshot=copy.deepcopy(snapshot),
                snapshotDigest=hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
                buildable=None, requiresNativePreview=True, routes=[], sites=[],
                supply=supply_balance(chains),
                warnings=[tr_text('历史调查数据；施工前重新读取会话、实体和端口。', 'Historical survey; refresh session, entities and ports before construction.'),
                          tr_text('采样地形与包围盒不证明碰撞、道路连通、站点覆盖或长期模拟安全。', 'Sampled terrain and bounds do not verify collisions, road connectivity, station coverage or long-term simulation safety.')],
                phases=[dict(name=tr_text('起步', 'Start'), actions=[tr_text('核实主城需求，选择一条短供给链', 'Verify town demand and select a short supply chain'), tr_text('接通末端配送，配置基本市内公交', 'Connect final delivery and basic town transit')], gate=tr_text('有效交付和接驳已验证，运行现金流可持续', 'Verify deliveries, connections and sustainable operating cash flow')),
                        dict(name=tr_text('协同', 'Coordination'), actions=[tr_text('比较邻城实际客流', 'Compare actual travel demand in neighboring towns'), tr_text('按合计需求配置干线、装卸与仓储', 'Size main routes, handling and storage for combined demand')], gate=tr_text('供给稳定且新增运输有真实需求', 'Stable supply and demonstrated demand for new transport')),
                        dict(name=tr_text('扩张', 'Expansion'), actions=[tr_text('补充升级后的需求', 'Meet demand after upgrades'), tr_text('按实际瓶颈扩容产业园、干线和配送', 'Expand production hubs, main routes and delivery at confirmed bottlenecks')], gate=tr_text('更新需求预测与预留空间，逐项原生预览', 'Refresh demand forecasts and reserved space; preview each operation natively'))])


def plan_global(snapshot, focus_town, neighbor_count=2, supply_chains=None):
    if snapshot.get('scope') == 'local':
        raise ValueError('global development requires a whole-map snapshot')
    if not isinstance(neighbor_count, int) or not 0 <= neighbor_count <= 10:
        raise ValueError('neighbor_count must be 0..10')
    towns = snapshot['map']['towns']
    focus = next((t for t in towns if t['id'] == focus_town), None)
    if focus is None:
        raise ValueError('focus_town not found in this snapshot')
    plan = base_plan(snapshot, str(focus.get("name", focus_town)) + " · " + tr_text("区域发展规划", "Regional development plan"), 'global', supply_chains or [])
    plan['focusTown'] = focus_town
    def xy(t):
        p = t['position']
        return (p['x'], p['y'])
    neighbors = sorted((t for t in towns if t['id'] != focus_town), key=lambda t: math.dist(xy(t), xy(focus)))[:neighbor_count]
    plan['neighbors'] = [dict(town=t['id'], name=t.get('name', str(t['id'])), distance=round(math.dist(xy(t), xy(focus)), 1), basis='straight-line distance only; demand and cost unknown') for t in neighbors]
    for t in neighbors:
        plan['routes'].append(dict(name=f"{focus.get('name', focus_town)} → {t.get('name', t['id'])}", mode='regional',
                                   path=[focus['position'], t['position']], status='concept',
                                   warning=tr_text('联系示意线，不是道路或铁路设计；需比较实际需求和成本。', 'Conceptual connection, not a road or rail design; compare actual demand and cost.')))
    plan['industryCandidates'] = [dict(i, distanceToFocus=round(math.dist(xy(i), xy(focus)), 1)) for i in sorted(snapshot['map'].get('industries', []), key=lambda t: math.dist(xy(t), xy(focus)))]
    plan['warnings'] += [tr_text('邻城按直线距离初筛；未把距离当作客流或盈利依据。', 'Neighboring towns screened by straight-line distance only, not passenger demand or profitability.'),
                         tr_text('产业类型不能证明配方、可供产量和城市需求；供给链需填入核实数据。', 'Industry types do not establish recipes, available output or town demand; use verified supply-chain data.'),
                         tr_text('原料产地分散、相关加工集中、成品分城配送；园区须另做局部选址与升级预留核验。', 'Connect dispersed raw materials to related processing and distribute finished goods by town; verify hub sites and upgrade space separately.')]
    return plan


def plan_local(snapshot, sites=None, corridors=None, supply_chains=None, title=None):
    if len(sites or []) > 100 or len(corridors or []) > 20:
        raise ValueError('limit each local plan to 100 sites and 20 corridors')
    plan = base_plan(snapshot, title if title is not None else tr_text('局部布局规划', 'Local layout plan'), 'local', supply_chains or [])
    terrain = Terrain(snapshot['grid'])
    bounds = grid_bounds(snapshot['grid'])
    obstacles = snapshot.get('obstacles', [])
    proposed = []
    names = set()
    for entry in sites or []:
        site = copy.deepcopy(entry)
        if site['name'] in names:
            raise ValueError('site names must be unique')
        names.add(site['name'])
        current, reserve = box(site['current']), box(site['reserved'])
        if not contains(reserve, current):
            raise ValueError('reserved must include the entire current footprint')
        if not site.get('basis'):
            raise ValueError('site basis must describe native dimensions or estimate')
        conflicts = [o['entity'] for o in obstacles if overlaps(reserve, o)]
        site['conflicts'] = conflicts
        site['siteConflicts'] = []
        site['outsideSurvey'] = not contains(bounds, reserve)
        site['status'] = 'needs_survey' if site['outsideSurvey'] else 'conflict' if conflicts else 'sampled_only'
        if not site['outsideSurvey']:
            # Include interior samples: corners alone miss water and ridges.
            g = snapshot['grid']
            nx = max(1, math.ceil((reserve['max']['x']-reserve['min']['x'])/g['spacing']))
            ny = max(1, math.ceil((reserve['max']['y']-reserve['min']['y'])/g['spacing']))
            samples = [terrain.sample(reserve['min']['x']+(reserve['max']['x']-reserve['min']['x'])*i/nx,
                                      reserve['min']['y']+(reserve['max']['y']-reserve['min']['y'])*j/ny)
                       for j in range(ny+1) for i in range(nx+1)]
            site['heightRange'] = [min(h for h, _ in samples), max(h for h, _ in samples)]
            site['waterSamples'] = sum(w for _, w in samples)
        for other in plan['sites']:
            if overlaps(reserve, other['reserved']):
                site['siteConflicts'].append(other['name'])
                other['siteConflicts'].append(site['name'])
                site['status'] = other['status'] = 'conflict'
        plan['sites'].append(site)
        proposed.append(dict(entity=site['name'], kind='RESERVATION', **reserve))
    for c in corridors or []:
        if c.get('mode') not in ('road', 'rail'):
            raise ValueError('local corridor mode must be road or rail; water routes need a navigability survey')
        start, end = c['start'], c['end']
        a = tuple(number(start[k], 'start', -1e9) for k in ('x', 'y'))
        b = tuple(number(end[k], 'end', -1e9) for k in ('x', 'y'))
        terrain.sample(*a); terrain.sample(*b)
        if math.dist(a, b) < 1:
            raise ValueError('corridor endpoints must be distinct')
        # Roads are crossings to review, not free connections; other bounds and upgrade reserves are avoided.
        hard = [o for o in obstacles if o['kind'] != 'BASE_EDGE'] + proposed
        diagnostic = None
        try:
            path = detour(a, b, hard, [], snapshot['grid'], terrain)
        except ValueError as exc:
            # Endpoint rounding can put an A* lattice connector outside a non-aligned survey edge.
            path = None
            diagnostic = str(exc)
        result = dict(name=c['name'], mode=c['mode'], status='no_candidate', path=[], endpoints=[start,end], requiresNativePreview=True)
        if diagnostic:
            result['warning'] = 'Expand survey bounds: '+diagnostic
        if path:
            samples = []
            for p, q in zip(path, path[1:]):
                samples.extend(segment_points(p, q, min(25, snapshot['grid']['spacing'])))
            samples = list(dict.fromkeys(samples))
            ground = [terrain.sample(x, y) for x, y in samples]
            result.update(status='corridor_only', path=[dict(x=x, y=y, z=h, water=w) for (x,y),(h,w) in zip(samples,ground)],
                          length=round(sum(math.dist(p,q) for p,q in zip(samples,samples[1:])),1),
                          waterSamples=sum(w for _,w in ground),
                          maxGroundGrade=max((abs(ground[i][0]-ground[i-1][0])/math.dist(samples[i],samples[i-1]) for i in range(1,len(samples))), default=0),
                          warning=tr_text('地表走廊，不是平纵断面设计；坡度为地表指标。桥隧、曲率及真实端口须另行设计预览。', 'Surface corridor only, not an alignment design; grades describe terrain. Bridges, tunnels, curvature and actual ports require separate design and preview.'))
            result['crossings'] = sorted({str(o['entity']) for o in obstacles if o['kind']=='BASE_EDGE' and any(o['min']['x']-20<=x<=o['max']['x']+20 and o['min']['y']-20<=y<=o['max']['y']+20 for x,y in samples)})
        plan['routes'].append(result)
    plan['warnings'].append(tr_text('预留区应包含升级建筑、出入口、维护及接驳通道；港口还需岸线和可航水域调查。', 'Reserve space for upgrades, entrances, maintenance and connections; harbors also require shoreline and navigable-water surveys.'))
    return plan
