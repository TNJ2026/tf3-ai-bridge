"""Explicit road graphs and paired carriageways; no implicit crossing or game writes."""
from __future__ import annotations

import math


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def vector(v):
    return isinstance(v, dict) and set(v) == {'x', 'y', 'z'} and all(number(x) for x in v.values())


def entity(v):
    return type(v) is int and 0 <= v < 2147483647


def junction(value):
    if not isinstance(value, dict) or not value or not value.keys() <= {'extend', 'phase_duration', 'signals', 'blocked_turns', 'crosswalk_edges'}:
        return False
    if {'blocked_turns', 'crosswalk_edges'} & value.keys():
        if 'signals' not in value or 'extend' in value:
            return False
        walks = value.get('crosswalk_edges', [])
        blocked = value.get('blocked_turns', [])
        if not isinstance(walks, list) or len(walks) > 8 or not all(entity(i) and i < 48 for i in walks) or len(set(walks)) != len(walks):
            return False
        if not isinstance(blocked, list) or len(blocked) > 56:
            return False
        pairs = set()
        for turn in blocked:
            if not isinstance(turn, dict) or set(turn) != {'from_edge', 'to_edge'}:
                return False
            pair = (turn['from_edge'], turn['to_edge'])
            if not all(entity(i) and i < 48 for i in pair) or pair[0] == pair[1] or pair in pairs:
                return False
            pairs.add(pair)
    if 'extend' in value and value['extend'] != 'preserve':
        return False
    if 'phase_duration' in value and (value.get('extend') != 'preserve' or not number(value['phase_duration']) or not 3 <= value['phase_duration'] <= 120):
        return False
    if 'signals' in value:
        s = value['signals']
        if not isinstance(s, dict) or set(s) != {'preference', 'traffic_light_type', 'states'} or s['preference'] != 'YES':
            return False
        if type(s['traffic_light_type']) is not int or not -1 <= s['traffic_light_type'] < 10000:
            return False
        if not isinstance(s['states'], list) or not 1 <= len(s['states']) <= 64:
            return False
        for phase in s['states']:
            if not isinstance(phase, dict) or set(phase) != {'locked_lanes', 'duration', 'min_duration', 'can_skip'}:
                return False
            locked = phase['locked_lanes']
            if not isinstance(locked, list) or len(locked) > 544 or not all(entity(i) and i < 544 for i in locked) or len(set(locked)) != len(locked):
                return False
            if not number(phase['duration']) or not number(phase['min_duration']) or not 0 <= phase['min_duration'] <= phase['duration'] <= 300 or phase['duration'] <= 0 or type(phase['can_skip']) is not bool:
                return False
    return True


def road_graph(value):
    """Indices are zero based on the wire. Require explicit topology and elevation."""
    if not isinstance(value, dict) or set(value) != {'nodes', 'edges'}:
        return False
    nodes, edges = value['nodes'], value['edges']
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 32 or not isinstance(edges, list) or not 0 <= len(edges) <= 48:
        return False
    identities = set()
    for n in nodes:
        if not isinstance(n, dict):
            return False
        if 'junction' in n and not junction(n['junction']):
            return False
        if 'crossing_resource' in n and (not isinstance(n['crossing_resource'], str) or not 1 <= len(n['crossing_resource']) <= 160 or 'junction' in n):
            return False
        source = set(n) - {'junction', 'crossing_resource'}
        if source == {'node'} and entity(n['node']):
            key = ('node', n['node'])
        elif source == {'position'} and vector(n['position']):
            key = ('position', *(n['position'][k] for k in ('x', 'y', 'z')))
        elif source == {'split'} and isinstance(n['split'], dict) and {'edge', 'param'} <= n['split'].keys() <= {'edge', 'param', 'preserve_objects', 'allow_structure', 'preserve_crossings', 'preserve_tunnel_chain'}:
            s = n['split']
            if not entity(s['edge']) or not number(s['param']) or not .05 <= s['param'] <= .95:
                return False
            if any(k in s and type(s[k]) is not bool for k in ('preserve_objects', 'allow_structure', 'preserve_crossings', 'preserve_tunnel_chain')):
                return False
            if s.get('preserve_tunnel_chain') and s.get('allow_structure') is not True:
                return False
            key = ('split', s['edge'])  # one split per old edge in a single proposal
        else:
            return False
        if key in identities:
            return False
        identities.add(key)
    used, pairs = set(), set()
    for e in edges:
        if not isinstance(e, dict) or not {'from', 'to', 'template'} <= e.keys() <= {
            'from', 'to', 'template', 'tangent0', 'tangent1', 'structure', 'structure_resource'}:
            return False
        a, b = e['from'], e['to']
        if not entity(a) or not entity(b) or a >= len(nodes) or b >= len(nodes) or a == b:
            return False
        pair = tuple(sorted((a, b)))
        if pair in pairs:
            return False
        pairs.add(pair)
        used.update(pair)
        if not isinstance(e['template'], str) or not 1 <= len(e['template']) <= 160:
            return False
        if any(k in e and not vector(e[k]) for k in ('tangent0', 'tangent1')):
            return False
        structure = e.get('structure', 'ground')
        if structure not in ('ground', 'bridge', 'tunnel'):
            return False
        if structure == 'ground':
            if 'structure_resource' in e:
                return False
        elif not isinstance(e.get('structure_resource'), str) or not 1 <= len(e['structure_resource']) <= 160:
            return False
    used.update(i for i, n in enumerate(nodes) if 'split' in n)
    return used == set(range(len(nodes)))


def paired_highway(centerline, template, lane_configs, median_gap=4.0, drive_side='right'):
    """Two physically separate one-way roads, including shoulders and lane widths.

    Centerline runs A -> B; carriageway 0 carries A -> B, 1 carries B -> A.
    Free endpoints are intentional; ramps/ports must be designed in the graph.
    """
    if not isinstance(centerline, list) or not 2 <= len(centerline) <= 16 or not all(vector(p) for p in centerline):
        raise ValueError('centerline requires 2-16 explicit xyz points')
    if not number(median_gap) or not 0 <= median_gap <= 100 or drive_side not in ('right', 'left'):
        raise ValueError('Invalid median gap or driving side')
    if not isinstance(template, str) or '/highway/' not in '/' + template:
        raise ValueError('Select an actual highway template')
    width, max_offset, forwards = 0.0, 0.0, set()
    for lane in lane_configs:
        if not all(number(lane.get(k)) for k in ('width', 'offset')) or lane['width'] <= 0:
            raise ValueError('Native lane width/offset unavailable')
        # TF3 lane offsets are not absolute positions across the road: the native
        # medium highway has widths [4,5,5,4] and four zero offsets. Summing all
        # lane strips includes shoulders. Reserve extra room for nonzero offsets
        # conservatively, pending native footprint checks for that template.
        width += lane['width']
        max_offset = max(max_offset, abs(lane['offset']))
        modes = lane.get('transportModes', {})
        def enabled(i):
            return modes.get(str(i), modes.get(i, False)) is True if isinstance(modes, dict) else False
        if any(enabled(i) for i in (2, 3, 4)):
            if type(lane.get('forward')) is not bool:
                raise ValueError('Native lane direction unavailable')
            forwards.add(lane['forward'])
    if len(forwards) != 1 or width <= 0:
        raise ValueError('Paired highway requires a confirmed one-way vehicle template')
    envelope_width = width + 2 * max_offset
    offset = envelope_width / 2 + median_gap / 2
    normals = []
    for a, b in zip(centerline, centerline[1:]):
        dx, dy = b['x'] - a['x'], b['y'] - a['y']
        length = math.hypot(dx, dy)
        if length < 10:
            raise ValueError('Degenerate centerline')
        normals.append((-dy / length, dx / length))
    miters = []
    for i in range(len(centerline)):
        a, b = normals[max(0, i-1)], normals[min(i, len(normals)-1)]
        nx, ny = a[0]+b[0], a[1]+b[1]
        norm = math.hypot(nx, ny)
        if norm < 1e-6:
            raise ValueError('Reversing centerline')
        nx, ny = nx/norm, ny/norm
        dot = nx*b[0] + ny*b[1]
        if dot < .8:
            raise ValueError('Highway bend too sharp; use a smoother centerline')
        miters.append((nx*offset/dot, ny*offset/dot))
    graph = {'nodes': [], 'edges': []}
    directions = []
    for carriageway in range(2):
        side = (-1 if drive_side == 'right' else 1) * (1 if carriageway == 0 else -1)
        points = [dict(x=p['x']+side*m[0], y=p['y']+side*m[1], z=p['z']) for p,m in zip(centerline, miters)]
        # Make template's native forward/backward lane direction match intended travel.
        reverse = (carriageway == 1) == next(iter(forwards))
        if reverse:
            points.reverse()
        base = len(graph['nodes'])
        graph['nodes'].extend({'position': p} for p in points)
        for i, (a, b) in enumerate(zip(points, points[1:])):
            length = math.hypot(b['x']-a['x'], b['y']-a['y'])
            if not 10 <= length <= 200:
                raise ValueError('Each offset span must be 10-200 m; resample the centerline')
            tangents = []
            for j in (i, i+1):
                prev, following = points[max(0,j-1)], points[min(len(points)-1,j+1)]
                dx,dy,dz=(following[k]-prev[k] for k in ('x','y','z'))
                norm = math.hypot(dx,dy)
                if norm < 1e-6:
                    raise ValueError('Offset carriageway reverses direction')
                tangents.append(dict(x=dx*length/norm,y=dy*length/norm,z=dz*length/norm))
            graph['edges'].append({'from': base+i, 'to': base+i+1, 'template': template,
                                   'tangent0': tangents[0], 'tangent1': tangents[1]})
        indices = list(range(base, base+len(points)))
        if not next(iter(forwards)):
            indices.reverse()
        directions.append({'carriageway': carriageway, 'travel': 'A_to_B' if carriageway == 0 else 'B_to_A',
                           'entry': indices[0], 'exit': indices[-1], 'nodes': indices})
    # Reject self-intersecting or touching centerlines/offsets (no automatic crossings).
    def cross(a,b,c):
        return (b['x']-a['x'])*(c['y']-a['y'])-(b['y']-a['y'])*(c['x']-a['x'])
    def distance(p,a,b):
        dx,dy=b['x']-a['x'],b['y']-a['y']
        t=max(0,min(1,((p['x']-a['x'])*dx+(p['y']-a['y'])*dy)/(dx*dx+dy*dy)))
        return math.hypot(p['x']-a['x']-t*dx,p['y']-a['y']-t*dy)
    edges = graph['edges']
    for i, e in enumerate(edges):
        a,b=(graph['nodes'][e[k]]['position'] for k in ('from','to'))
        for f in edges[i+1:]:
            if {e['from'],e['to']} & {f['from'],f['to']}:
                continue
            c,d=(graph['nodes'][f[k]]['position'] for k in ('from','to'))
            crossing = cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0
            clearance=min(distance(a,c,d),distance(b,c,d),distance(c,a,b),distance(d,a,b))
            if crossing or clearance < envelope_width-1e-6:
                raise ValueError('Carriageways overlap; revise the highway corridor')
    if not road_graph(graph):
        raise ValueError('Generated highway graph exceeds bounds')
    return {'graph': graph, 'directions': directions, 'native_lane_width': width,
            'envelope_width': envelope_width, 'center_offset': offset, 'median_gap_minimum': median_gap,
            'nativePreviewPassed': False, 'directedPathsVerified': False}
