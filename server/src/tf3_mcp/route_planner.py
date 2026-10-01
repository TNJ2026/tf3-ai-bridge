"""Read-only rail candidate ranking. No game calls, commands, or hidden retries."""
from __future__ import annotations
import math
import time
from collections import Counter, defaultdict


def _unit(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d else (0., 0.)


def _curve(anchors, first, last, step=35):
    directions = [first]
    directions += [_unit(anchors[i+1][0]-anchors[i-1][0], anchors[i+1][1]-anchors[i-1][1]) for i in range(1, len(anchors)-1)]
    directions.append(last)
    if len(anchors) >= 5:
        directions[1], directions[-2] = first, last
    out = []
    for i, (a, b) in enumerate(zip(anchors, anchors[1:])):
        length = math.dist(a, b)
        if length < 1:
            return []
        n = max(2, math.ceil(length / step))
        for j in range(n):
            t = j / n
            h = (2*t**3-3*t*t+1, t**3-2*t*t+t, -2*t**3+3*t*t, t**3-t*t)
            out.append(tuple(h[0]*a[k]+h[1]*length*directions[i][k]+h[2]*b[k]+h[3]*length*directions[i+1][k] for k in (0, 1)))
    return out + [anchors[-1]]


class Terrain:
    def __init__(self, grid):
        self.g = grid

    def sample(self, x, y):
        g = self.g
        u, v = (x-g['x'])/g['spacing'], (y-g['y'])/g['spacing']
        if not (0 <= u <= g['nx']-1 and 0 <= v <= g['ny']-1):
            raise ValueError('outside snapshot')
        i, j = min(int(u), g['nx']-2), min(int(v), g['ny']-2)
        u, v = u-i, v-j
        indices = [j*g['nx']+i, j*g['nx']+i+1, (j+1)*g['nx']+i, (j+1)*g['nx']+i+1]
        weights = [(1-u)*(1-v), u*(1-v), (1-u)*v, u*v]
        return sum(g['heights'][k]*w for k,w in zip(indices,weights)), any(g['water'][k] for k in indices)


class Obstacles:
    """Spatial buckets keep candidate scoring independent of total map size."""
    def __init__(self, rows, cell=100):
        self.rows, self.cell, self.buckets = rows, cell, defaultdict(list)
        for n, row in enumerate(rows):
            lo, hi = row['min'], row['max']
            for x in range(math.floor((lo['x']-20)/cell), math.floor((hi['x']+20)/cell)+1):
                for y in range(math.floor((lo['y']-20)/cell), math.floor((hi['y']+20)/cell)+1):
                    self.buckets[x,y].append(n)

    def conflicts(self, x, y, z):
        for n in self.buckets.get((math.floor(x/self.cell),math.floor(y/self.cell)), ()):
            r = self.rows[n]; lo, hi = r['min'], r['max']
            # Road crossings need vertical clearance; buildings are avoided entirely.
            if lo['x']-20 <= x <= hi['x']+20 and lo['y']-20 <= y <= hi['y']+20:
                if r['kind'] != 'BASE_EDGE' or lo['z']-10 < z < hi['z']+10:
                    yield r['entity']


def plan_routes(snapshot, *, max_candidates=3, max_grade=.025, min_radius=120):
    """Compare all free port pairs and lateral detours against ONE immutable snapshot.

    Results are approximate survey candidates, never permission to skip native preview.
    Sampling is conservative but cannot prove clearance or curvature between samples.
    """
    if not 1 <= max_candidates <= 10 or not .005 <= max_grade <= .06 or min_radius < 30:
        raise ValueError('invalid planning limits')
    started = time.perf_counter()
    terrain, obstacles = Terrain(snapshot['grid']), Obstacles(snapshot['obstacles'])
    stations = snapshot['stations']
    results, rejected, tested = [], Counter(), 0
    for start in stations[0]['ports']:
        for end in stations[1]['ports']:
            a, b = start['position'], end['position']
            da = _unit(start['direction']['x'],start['direction']['y'])
            db = _unit(end['direction']['x'],end['direction']['y'])
            direct = math.hypot(b['x']-a['x'],b['y']-a['y'])
            if direct < 300:
                rejected['stations_too_close'] += 1
                continue
            normal = (-(b['y']-a['y'])/direct,(b['x']-a['x'])/direct)
            for offset in (0, -400, 400, -800, 800, -1400, 1400):
                # Fixed stubs keep tunnel portals and turns away from station ends.
                anchors = [(a['x'],a['y']), (a['x']+da[0]*600,a['y']+da[1]*600),
                           ((a['x']+b['x'])/2+normal[0]*offset,(a['y']+b['y'])/2+normal[1]*offset),
                           (b['x']+db[0]*600,b['y']+db[1]*600),(b['x'],b['y'])]
                xy = _curve(anchors,da,(-db[0],-db[1]))
                if not xy:
                    continue
                distance = [0.]
                for p,q in zip(xy,xy[1:]): distance.append(distance[-1]+math.dist(p,q))
                # Discrete curvature rejects hairpins before the expensive obstacle checks.
                radii = []
                for p,q,r in zip(xy,xy[1:],xy[2:]):
                    x,y,z = math.dist(p,q), math.dist(q,r), math.dist(p,r)
                    cross = abs((q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]))
                    if cross > 1e-7: radii.append(x*y*z/(2*cross))
                if radii and min(radii) < min_radius:
                    rejected['curve_radius'] += 1
                    continue
                try: ground = [terrain.sample(*p) for p in xy]
                except ValueError:
                    rejected['outside_snapshot'] += 1
                    continue
                for lift in (0, 12, 24):
                    tested += 1
                    total = distance[-1]
                    if abs(b['z']-a['z']) > total*max_grade:
                        rejected['grade'] += 1; continue
                    # Constant design elevation with bounded approach grades.
                    level = max(a['z'],b['z'])+lift
                    zs = [min(level,a['z']+d*max_grade,b['z']+(total-d)*max_grade) for d in distance]
                    zs[0],zs[-1] = a['z'],b['z']
                    blocked = set()
                    for (x,y),z in zip(xy,zs): blocked.update(obstacles.conflicts(x,y,z))
                    if blocked:
                        rejected['obstacle'] += 1; continue
                    bridge = tunnel = earth = 0.
                    path = []
                    for i,((x,y),z,(h,water)) in enumerate(zip(xy,zs,ground)):
                        length = distance[i]-distance[i-1] if i else 0
                        typ = 'tunnel' if h-z > 7 else 'bridge' if water or z-h > 7 else 'ground'
                        if typ == 'bridge': bridge += length
                        elif typ == 'tunnel': tunnel += length
                        else: earth += abs(z-h)*length
                        path.append(dict(x=x,y=y,z=z,h=h,water=water,structure=typ))
                    results.append(dict(startNode=start['node'],endNode=end['node'],length=round(total,1),
                        score=round(total+bridge*1.5+tunnel*2+earth*.15,1),bridgeLength=round(bridge,1),
                        tunnelLength=round(tunnel,1),minSampledRadius=round(min(radii,default=1e9),1),
                        maxGrade=max(abs(zs[i]-zs[i-1])/(distance[i]-distance[i-1]) for i in range(1,len(zs))),
                        path=path,requiresNativePreview=True))
    results.sort(key=lambda r:r['score'])
    # Keep different endpoint/route options rather than filling the list with elevations of one route.
    selected, seen = [], set()
    for r in results:
        mid=r['path'][len(r['path'])//2]; key=(r['startNode'],r['endNode'],round(mid['x']/100),round(mid['y']/100))
        if key not in seen: selected.append(r); seen.add(key)
        if len(selected) == max_candidates: break
    return dict(candidates=selected,requiresNativePreview=True,buildable=None,
                stats=dict(localSeconds=round(time.perf_counter()-started,4),evaluated=tested,
                           locallyClear=len(results),rejected=dict(rejected),obstacles=len(snapshot['obstacles'])),
                snapshotState=snapshot.get('state'),
                limitation='Approximate sampled routes; refresh endpoints and run native collision/grade preview before building. No route means expand the corridor or use a more detailed search.')
