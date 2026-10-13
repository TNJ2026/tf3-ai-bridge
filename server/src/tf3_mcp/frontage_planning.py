"""Bounded roadside siting. Geometry only: no game writes or implicit approvals.

Road facilities align their native external port with a point on the original
Hermite curve. Air facilities align the native collider with the road envelope.
The workflow must independently preview/build/verify the selected candidate.
"""
from __future__ import annotations

import hashlib
import math
import re
import zipfile
from pathlib import Path

RESOURCES = {
    'road_depot': '::/depots/road/road_depot/road_depot.con',
    'tram_depot': '::/depots/road/tram_depot/tram_depot.con',
    'cargo_station': '::/stations/street/modular_street_station/modular_terminal.con',
    'passenger_station': '::/stations/street/modular_street_station/modular_terminal.con',
    'heliport': '::/stations/air/heliport.con',
    'helipad': '::/stations/air/helipad.con',
}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def curve(edge, t):
    if not finite(t) or not 0 <= t <= 1:
        raise ValueError('Curve parameter must be in [0,1]')
    a, b, u, v = (edge[k] for k in ('position0', 'position1', 'tangent0', 'tangent1'))
    if not all(finite(p[k]) for p in (a, b, u, v) for k in 'xyz'):
        raise ValueError('Complete finite native curve required')
    weights = (2*t**3-3*t*t+1, -2*t**3+3*t*t, t**3-2*t*t+t, t**3-t*t)
    deriv = (6*t*t-6*t, -6*t*t+6*t, 3*t*t-4*t+1, 3*t*t-2*t)
    return tuple({k: sum(w*p[k] for w, p in zip(ws, (a,b,u,v))) for k in 'xyz'}
                 for ws in (weights, deriv))


def project(edge, x, y):
    """Bounded global coarse scan followed by local golden-section refinement."""
    if not finite(x) or not finite(y):
        raise ValueError('Finite target coordinates required')
    def distance(t):
        p, _ = curve(edge, t)
        return (p['x']-x)**2+(p['y']-y)**2
    values = [i/100 for i in range(101)]
    best = min(range(len(values)), key=lambda i: distance(values[i]))
    lo, hi = values[max(0,best-1)], values[min(100,best+1)]
    for _ in range(40):
        a, b = lo+(hi-lo)*.38196601125, lo+(hi-lo)*.61803398875
        if distance(a) < distance(b): hi = b
        else: lo = a
    return (lo+hi)/2


def road_half_width(lanes):
    if not lanes or not all(finite(l.get('width')) and l['width'] > 0
                            and finite(l.get('offset')) for l in lanes):
        raise ValueError('Native lane widths and offsets required')
    return sum(l['width'] for l in lanes)/2 + max(abs(l['offset']) for l in lanes)


def native_collider(content: Path, kind: str):
    """Read data literals only; do not execute game assets in the host process."""
    family = 'stations/air' if kind in ('heliport','helipad') else 'depots/road'
    if kind not in ('heliport','helipad','road_depot','tram_depot'):
        raise ValueError('No static collider for modular terminal')
    member = f"{family.rsplit('/',1)[1]}/{kind}/{kind}.script.lua"
    with zipfile.ZipFile(content / (family+'.zip')) as archive:
        raw = archive.read(member)
    source = raw.decode('utf-8')
    match = re.search(r'\["collider"\]\s*=\s*\{', source)
    if not match: raise ValueError('Native collider literal missing')
    start, depth, end = match.end()-1, 0, None
    for i in range(start, len(source)):
        depth += (source[i] == '{') - (source[i] == '}')
        if depth == 0:
            end = i+1
            break
    if end is None: raise ValueError('Incomplete collider')
    number = r'(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    points = [tuple(map(float,m)) for m in re.findall(
        r'\{\s*'+number+r'\s*,\s*'+number+r'\s*,\s*'+number+r'\s*\}',source[start:end])]
    if len(points) < 4: raise ValueError('Unsupported native collider literal')
    return {'bounds': [min(p[0] for p in points), max(p[0] for p in points),
                       min(p[1] for p in points), max(p[1] for p in points)],
            'source': member, 'sha256': hashlib.sha256(raw).hexdigest()}


def external_port(construction, edges):
    """Extract local port from a freshly read, matching current construction."""
    columns = construction['transf']['columns']
    if len(columns) != 4: raise ValueError('Native transform unavailable')
    a,b,_,origin = columns
    if abs(a['x']*b['y']-a['y']*b['x']-1) > 1e-4:
        raise ValueError('Unsupported scaled/tilted native transform')
    ports = {}
    for edge in edges:
        for i in (0,1):
            if edge[f'node{i}'] not in construction['frozenNodes']:
                p = edge[f'position{i}']
                dx,dy = p['x']-origin['x'],p['y']-origin['y']
                ports[edge[f'node{i}']] = {'x': dx*a['x']+dy*a['y'],
                    'y': dx*b['x']+dy*b['y'], 'z': p['z']-origin['z']}
    if len(ports) != 1: raise ValueError('Unique external native port required')
    return next(iter(ports.values()))


def candidates(edge, profile, *, param=.5, side='auto', search=True):
    if not finite(param) or not 0 <= param <= 1 or side not in ('auto','left','right'):
        raise ValueError('Invalid target parameter or side')
    half_width = road_half_width(edge['laneConfigs'])
    ts = [param]
    if search: ts += [param-.1,param+.1,param-.2,param+.2,.5]
    out, seen = [], set()
    for t in ts:
        if not .05 <= t <= .95 or round(t,8) in seen: continue
        seen.add(round(t,8))
        p,tangent = curve(edge,t)
        if min(math.hypot(p['x']-edge[k]['x'],p['y']-edge[k]['y'])
               for k in ('position0','position1')) < 5: continue
        if math.hypot(tangent['x'],tangent['y']) < 1e-6: continue
        for s in (('left','right') if side == 'auto' else (side,)):
            angle = math.atan2(tangent['y'],tangent['x'])+(math.pi if s=='right' else 0)
            c,sn = math.cos(angle), math.sin(angle)
            if profile['kind'] in ('heliport','helipad'):
                port = {'x':0, 'y':profile['bounds'][2]-half_width, 'z':0}
            else:
                port = profile['port']
            x,y = p['x']-c*port['x']+sn*port['y'],p['y']-sn*port['x']-c*port['y']
            out.append({'param':t,'side':s,'target':p,'x':x,'y':y,'z':p['z']-port['z'],
                        'rotation':math.degrees(angle)%360,'roadHalfWidth':half_width,
                        'shiftFromRequestedParam':abs(t-param), 'nativePreviewPassed':False})
    return out


def footprint_contains(candidate, bounds, point, margin=0):
    a = math.radians(candidate['rotation']);c,s = math.cos(a),math.sin(a)
    dx,dy = point['x']-candidate['x'],point['y']-candidate['y']
    x,y = c*dx+s*dy,-s*dx+c*dy
    return bounds[0]-margin <= x <= bounds[1]+margin and bounds[2]-margin <= y <= bounds[3]+margin


def safe_preview(p):
    return (p.get('ok') is True and bool(p.get('preview_token')) and finite(p.get('cost'))
            and p['cost'] >= 0 and not any(p.get(k) for k in
                ('critical','blocked','placementBlocked','collisions','warnings','unexpected_removals')))
