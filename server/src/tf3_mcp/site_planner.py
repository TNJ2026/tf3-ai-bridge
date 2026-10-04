"""Bounded, offline batch siting. Candidates are alternatives, never build approvals."""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict

from .development_planner import base_plan, box, contains, grid_bounds, number
from .planning_geometry import dry_access
from .route_planner import Terrain
from .flat_areas import FlatTerrain, preference_key, POLICY_VERSION


def touches(a, b):
    return all(a['min'][k] <= b['max'][k] and a['max'][k] >= b['min'][k] for k in ('x', 'y'))


class BoxIndex:
    """Bounded buckets; unusually large objects stay in a small overflow list."""
    def __init__(self, rows, cell=100):
        self.rows, self.cell = rows, cell
        self.buckets, self.large = defaultdict(list), []
        self.checks = 0
        for i, row in enumerate(rows):
            x0, y0, x1, y1 = self.cells(row)
            if (x1-x0+1)*(y1-y0+1) > 256:
                self.large.append(i)
            else:
                for x in range(x0, x1+1):
                    for y in range(y0, y1+1):
                        self.buckets[x, y].append(i)

    def cells(self, b):
        return tuple(math.floor(b[end][axis]/self.cell)
                     for end, axis in [('min','x'),('min','y'),('max','x'),('max','y')])

    def blocked(self, b, host=None):
        x0, y0, x1, y1 = self.cells(b)
        if (x1-x0+1)*(y1-y0+1) > 256:
            ids = range(len(self.rows))
        else:
            ids = set(self.large)
            for x in range(x0, x1+1):
                for y in range(y0, y1+1):
                    ids.update(self.buckets.get((x,y), ()))
        for i in sorted(ids):
            row = self.rows[i]
            # Only the explicitly selected supporting edge may overlap a roadside stop.
            if host is not None and row.get('kind') == 'BASE_EDGE' and row.get('entity') == host:
                continue
            self.checks += 1
            if touches(b, row):
                return True
        return False


def transformed(b, x, y, rotation):
    a = math.radians(rotation)
    co, si = math.cos(a), math.sin(a)
    points = [(x+px*co-py*si, y+px*si+py*co)
              for px in (b['min']['x'], b['max']['x'])
              for py in (b['min']['y'], b['max']['y'])]
    return dict(min=dict(x=min(p[0] for p in points), y=min(p[1] for p in points)),
                max=dict(x=max(p[0] for p in points), y=max(p[1] for p in points)))


def curve(edge, t):
    weights = (2*t**3-3*t*t+1, t**3-2*t*t+t, -2*t**3+3*t*t, t**3-t*t)
    return tuple(sum(w*edge[key][axis] for w,key in zip(weights, ('position0','tangent0','position1','tangent1')))
                 for axis in ('x','y'))


def search_sites(snapshot, requests, max_candidates=3, max_evaluations=10000, reserved_areas=None):
    if not isinstance(requests, list) or not 1 <= len(requests) <= 20:
        raise ValueError('requests must contain 1..20 site searches')
    for value, name, hi in [(max_candidates, 'max_candidates', 10), (max_evaluations, 'max_evaluations', 20000)]:
        if type(value) is not int or not 1 <= value <= hi:
            raise ValueError(f'{name} must be an integer in 1..{hi}')
    started = time.perf_counter()
    plan = base_plan(snapshot, '设施批量选址 · 候选比较', 'local', [])
    g = snapshot['grid']
    terrain = Terrain(g)
    flat_terrain = FlatTerrain(g)
    bounds = grid_bounds(g)
    if not isinstance(reserved_areas or [], list) or len(reserved_areas or []) > 100:
        raise ValueError('reserved_areas must contain at most 100 boxes')
    rows = list(snapshot.get('obstacles', []))
    rows += [dict(box(area), kind='RESERVATION') for area in reserved_areas or []]
    for row in rows:
        if any(row['min'][k] > row['max'][k] for k in ('x','y')):
            raise ValueError('inverted obstacle bounds')
    index = BoxIndex(rows)
    edges = {r['entity']: r for r in rows if r.get('kind') == 'BASE_EDGE'}
    plan['searches'] = []
    plan['warnings'] += ['各候选为互斥备选，不是同时放置方案；选定后用局部规划核对设施间冲突。',
                         '默认平整优先排名使用采样地表坡度、高差与目标距离，不证明服务覆盖、接驳、成本或可施工。',
                         '停靠点道路类型、可建区间和既有边对象需实时核验；仅暂排除指定承载边。']
    names, total, terrain_work = set(), 0, 0
    for request in requests:
        name = request['name']
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('request names must be nonempty and unique')
        names.add(name)
        kind = request.get('kind', 'facility')
        if kind not in ('facility', 'street_stop'):
            raise ValueError('kind must be facility or street_stop; water facilities require a separate survey')
        if not isinstance(request.get('basis'), str) or not request['basis'].strip():
            raise ValueError('basis must describe dimensions and upgrade/access allowance')
        current, reserved = box(request['current']), box(request['reserved'])
        if not contains(reserved, current):
            raise ValueError('reserved must contain current, in local coordinates')
        x, y = (number(request['target'][k], 'target', -1e9) for k in ('x','y'))
        radius = number(request.get('radius', 300), 'radius', 1)
        if radius > 5000:
            raise ValueError('radius must be <= 5000 metres')
        max_height = number(request.get('max_height_range', 5), 'max_height_range')
        ranking = request.get('ranking', 'flat_first')
        if ranking not in ('flat_first','distance_height'):
            raise ValueError('ranking must be flat_first or distance_height')
        separation = number(request.get('min_separation', 50), 'min_separation')
        rotations = request.get('rotations', [0,90])
        if not isinstance(rotations, list) or not 1 <= len(rotations) <= 8:
            raise ValueError('rotations must contain 1..8 degrees')
        rotations = list(dict.fromkeys(number(v, 'rotation', -360) for v in rotations))
        if any(v > 360 for v in rotations):
            raise ValueError('rotation must be -360..360')
        positions = []
        access = request.get('access')
        if access is not None:
            if kind != 'facility':
                raise ValueError('access is for facilities; street stops use their supporting edge')
            for point in ('anchor', 'local_entry'):
                for axis in ('x', 'y'):
                    number(access[point][axis], 'access coordinate', -1e9)
            access_grade = number(access.get('max_grade', .10), 'access grade', .001)
            if access_grade > 1:
                raise ValueError('access grade must be <= 1')
        if kind == 'street_stop':
            ids = request.get('edges', [])
            if not isinstance(ids, list) or not 1 <= len(ids) <= 200:
                raise ValueError('street_stop requires 1..200 explicitly surveyed street edge IDs')
            for eid in dict.fromkeys(ids):
                edge = edges.get(eid)
                if edge is None:
                    raise ValueError('edge not found in snapshot')
                for key in ('position0','position1','tangent0','tangent1'):
                    for axis in ('x','y'):
                        number(edge[key][axis], 'edge geometry', -1e9)
                for t in (.25, .5, .75):
                    px, py = curve(edge, t)
                    before, after = curve(edge, t-.001), curve(edge, t+.001)
                    angle = math.degrees(math.atan2(after[1]-before[1], after[0]-before[0]))
                    if math.hypot(px-x,py-y) <= radius:
                        positions.append((px,py,angle,eid,t))
        else:
            step = number(request.get('step', 25), 'step', 10)
            n = math.floor(radius/step)
            if (2*n+1)**2 * len(rotations) > max_evaluations-total:
                raise ValueError('search budget exceeded; shrink radius or increase step')
            for i in range(-n,n+1):
                for j in range(-n,n+1):
                    if math.hypot(i*step,j*step) <= radius:
                        positions.extend((x+i*step,y+j*step,r,None,None) for r in rotations)
        if len(positions) > max_evaluations-total:
            raise ValueError('batch search budget exceeded')
        rejected, viable = Counter(), []
        for px, py, rotation, host, param in positions:
            total += 1
            footprint = transformed(current,px,py,rotation)
            reserve = transformed(reserved,px,py,rotation)
            if not contains(bounds,reserve):
                rejected['outside_survey'] += 1; continue
            if index.blocked(reserve,host):
                rejected['obstacle_or_reservation'] += 1; continue
            # Every supporting grid vertex, including the interior, contributes to the check.
            i0 = max(0,math.floor((reserve['min']['x']-g['x'])/g['spacing']))
            j0 = max(0,math.floor((reserve['min']['y']-g['y'])/g['spacing']))
            i1 = min(g['nx']-1,math.ceil((reserve['max']['x']-g['x'])/g['spacing']))
            j1 = min(g['ny']-1,math.ceil((reserve['max']['y']-g['y'])/g['spacing']))
            terrain_work += (i1-i0+1)*(j1-j0+1)
            if terrain_work > 2000000:
                raise ValueError('terrain work budget exceeded; shrink search or footprint')
            cells = [j*g['nx']+i for j in range(j0,j1+1) for i in range(i0,i1+1)]
            if any(g['water'][i] for i in cells):
                rejected['water'] += 1; continue
            lo, hi = min(g['heights'][i] for i in cells), max(g['heights'][i] for i in cells)
            if hi-lo > max_height:
                rejected['height_range'] += 1; continue
            profile = flat_terrain.profile(reserve, max_height)
            access_profile = profile
            entry = None
            if access is not None:
                a = math.radians(rotation)
                ex, ey = access['local_entry']['x'], access['local_entry']['y']
                entry = dict(x=px+ex*math.cos(a)-ey*math.sin(a),
                             y=py+ex*math.sin(a)+ey*math.cos(a))
                reason = dry_access(terrain, access['anchor'], entry, access_grade)
                if reason:
                    rejected[reason] += 1; continue
                access_profile = flat_terrain.profile(dict(
                    min={a:min(access['anchor'][a],entry[a])for a in ('x','y')},
                    max={a:max(access['anchor'][a],entry[a])for a in ('x','y')}))
            distance = math.hypot(px-x,py-y)
            candidate = dict(name=name, role=kind, current=footprint, reserved=reserve,
                             basis=request['basis'], position=dict(x=px,y=py), rotation=rotation,
                             distance=round(distance,2), heightRange=[lo,hi], score=distance+20*(hi-lo),
                             status='sampled_only', buildable=None, conflicts=[], siteConflicts=[],
                             requiresNativePreview=True)
            candidate.update(terrain=profile,ranking=ranking,rankingPolicy=POLICY_VERSION)
            if access is not None:candidate['accessTerrain']=access_profile
            if entry is not None:
                candidate['access'] = dict(anchor=access['anchor'], entry=entry,
                    status='dry_terrain_screen_only', native_verified=False,
                    requiresEndpointCollisionAndPathVerification=True)
            if host is not None:
                candidate.update(edge=host,param=param,requiresStreetValidation=True)
            viable.append(candidate)
        selected = []
        def rank(c):
            return preference_key(c['terrain'],c.get('accessTerrain',c['terrain']),c['distance']) if ranking=='flat_first' else (c['score'],)
        for candidate in sorted(viable,key=rank):
            p = candidate['position']
            if any(math.hypot(p['x']-c['position']['x'],p['y']-c['position']['y']) < separation for c in selected):
                continue
            candidate['name'] = f'{name} · 候选 {len(selected)+1}'
            selected.append(candidate)
            if len(selected) == max_candidates:
                break
        plan['sites'].extend(selected)
        plan['searches'].append(dict(name=name, evaluated=len(positions), rejected=dict(rejected),
                                     viable=len(viable), candidates=selected,
                                     status='candidates' if selected else 'no_candidate'))
    plan['metrics'] = dict(evaluated=total, obstacleChecks=index.checks, terrainVertices=terrain_work,
                           elapsedSeconds=round(time.perf_counter()-started,4), gameCalls=0)
    return plan
