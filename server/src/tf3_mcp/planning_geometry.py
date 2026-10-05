"""Pure geometry shared by early selection and full-map preflight. No game calls."""
import math


def polygon(bounds, position=None, rotation=0):
    position = position or {'x': 0, 'y': 0}
    a = math.radians(rotation)
    c, s = math.cos(a), math.sin(a)
    return [{'x': position['x'] + x*c-y*s, 'y': position['y'] + x*s+y*c}
            for x, y in [(bounds['min']['x'], bounds['min']['y']),
                         (bounds['max']['x'], bounds['min']['y']),
                         (bounds['max']['x'], bounds['max']['y']),
                         (bounds['min']['x'], bounds['max']['y'])]]


def intersects(a, b):
    """SAT for convex polygons; touching borders do not consume area."""
    for p in (a, b):
        for x, y in zip(p, p[1:]+p[:1]):
            nx, ny = x['y']-y['y'], y['x']-x['x']
            aa = [v['x']*nx+v['y']*ny for v in a]
            bb = [v['x']*nx+v['y']*ny for v in b]
            if max(aa) <= min(bb)+.01 or max(bb) <= min(aa)+.01:
                return False
    return True


def facility_polygon(row, key):
    # Existing whole-map plans store an unrotated world-centred rectangle.
    # Recompute from coordinates; never trust a polygon left over after a move.
    b, p = row[key], row['position']
    local = {end: {axis: b[end][axis]-p[axis] for axis in ('x', 'y')}
             for end in ('min', 'max')}
    return polygon(local, p, row.get('rotation', 0))


def facility_aabb(row, key='reserved'):
    """World-axis bounds for coarse obstacle indexes, after the facility rotation."""
    points = facility_polygon(row, key)
    return {'min': {a: min(p[a] for p in points) for a in ('x', 'y')},
            'max': {a: max(p[a] for p in points) for a in ('x', 'y')}}


def dry_access(terrain, start, end, max_grade=.10, step=10):
    """Cheap same-bank/grade screen before committing to a site; not pathfinding."""
    distance = math.hypot(end['x']-start['x'], end['y']-start['y'])
    n = max(1, math.ceil(distance/step))
    if n > 10000:
        return 'access_sampling_budget'
    last = None
    for i in range(n+1):
        x = start['x']+(end['x']-start['x'])*i/n
        y = start['y']+(end['y']-start['y'])*i/n
        try:
            z, water = terrain.sample(x, y)
        except ValueError:
            return 'access_outside_survey'
        if water:
            return 'access_crosses_water'
        if last is not None and distance > .01 and abs(z-last)/(distance/n) > max_grade:
            return 'access_grade_requires_design'
        last = z
    return None
