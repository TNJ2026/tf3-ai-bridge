"""Pure planning input checks and reusable template preparation. No game access."""
import copy
import json
import math
from pathlib import Path
from fullmap_workflow import digest

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / 'config/planning_templates'
FACILITY_HALF_SIZES = {'heliport': (55, 60), 'warehouse': (48, 42),
                       'truck': (45, 32), 'bus': (28, 30), 'road_depot': (26, 20),
                       'helipad': (18, 19), 'helipad2': (18, 19), 'road_maintenance': (16, 16)}


def facility_bounds(facility, sizes=FACILITY_HALF_SIZES, reserved=False):
    """Unrotated, facility-local estimated bounds; padding rotates with the building."""
    sx, sy = sizes[facility['role']]
    bounds = facility.get('footprintBounds', dict(min=dict(x=-sx, y=-sy), max=dict(x=sx, y=sy)))
    if (not isinstance(bounds, dict) or set(bounds) != {'min', 'max'} or
        any(not isinstance(bounds[s], dict) or set(bounds[s]) != {'x', 'y'} for s in ('min', 'max')) or
        any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for s in ('min', 'max') for v in bounds[s].values()) or
        any(bounds['min'][a] >= bounds['max'][a] for a in ('x', 'y'))):
        raise ValueError('Invalid facility footprint bounds: '+facility['role'])
    padding = facility.get('upgradeReserveM', {})
    allowed = {'minX', 'maxX', 'minY', 'maxY'}
    if not isinstance(padding, dict) or set(padding) - allowed:
        raise ValueError('Invalid upgrade reserve fields: '+facility['role'])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v < 0 for v in padding.values()):
        raise ValueError('Upgrade reserve must be finite and nonnegative: '+facility['role'])
    p = padding if reserved else {}
    return dict(min=dict(x=bounds['min']['x']-p.get('minX', 0), y=bounds['min']['y']-p.get('minY', 0)),
                max=dict(x=bounds['max']['x']+p.get('maxX', 0), y=bounds['max']['y']+p.get('maxY', 0)))


def positioned_bounds(facility, position, sizes=FACILITY_HALF_SIZES, reserved=False):
    """Plan convention: translate local bounds; downstream rotates once about position."""
    bounds = facility_bounds(facility, sizes, reserved)
    return {side: {axis: position[axis]+bounds[side][axis] for axis in ('x', 'y')}
            for side in ('min', 'max')}


def load_templates(city_path, production_path):
    """Read explicit portable template files; no machine-local export registry."""
    templates = {}
    for kind, path in (('city', city_path), ('production', production_path)):
        try:
            value = json.loads(Path(path).read_text(encoding='utf8'))
        except (OSError, ValueError) as exc:
            raise ValueError(f'Cannot read {kind} template {path}: {exc}') from exc
        templates[kind] = prepare_template(strip_native_evidence(value), kind)
    return templates


def prepare_template(template, kind):
    result = copy.deepcopy(template)
    from road_snap_layout import validate_road_snaps
    roles = {f['role']: f for f in result['facilities']}
    required = {'heliport', 'warehouse', 'truck', 'bus', 'road_depot'} if kind == 'city' else {'helipad', 'helipad2', 'warehouse', 'truck'}
    city_roles = {'heliport', 'warehouse', 'truck', 'bus', 'road_depot'}
    allowed = [required, required | {'road_maintenance'}] if kind == 'city' else [required, city_roles | {'road_maintenance'}, {'heliport', 'warehouse', 'truck', 'road_maintenance'}]
    if set(roles) not in allowed or len(roles) != len(result['facilities']):
        raise ValueError('Incomplete or duplicate collection roles: '+kind)
    if not result.get('roads'):
        raise ValueError('Collection frontage roads missing')
    nodes = {}
    for facility in roles.values():
        facility_bounds(facility)
        if not facility.get('resource') or not isinstance(facility.get('params'), dict):
            raise ValueError('Facility resource/params missing: '+facility['role'])
        for number in (*[facility['localPosition'][a] for a in ('x','y')], facility['relativeRotation']):
            if not isinstance(number, (int,float)) or not math.isfinite(number):
                raise ValueError('Invalid facility geometry: '+facility['role'])
    for road in result['roads']:
        if not road.get('roadTemplate'):raise ValueError('Road template missing')
        for end in (0,1):
            node=road['node'+str(end)];point=road['position'+str(end)]
            xy=tuple(point[a] for a in ('x','y'))
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in xy):raise ValueError('Invalid road geometry')
            if node in nodes and nodes[node]!=xy:raise ValueError('Template node has inconsistent coordinates: '+str(node))
            nodes[node]=xy
    validate_road_snaps(result)
    if any(f.get('upgradeReserveM') for f in result['facilities']):
        from tf3_mcp.planning_geometry import polygon, intersects
        reserves = [(f['role'], polygon(facility_bounds(f, reserved=True),
                    f['localPosition'], f['relativeRotation'])) for f in result['facilities']]
        for i, (role, shape) in enumerate(reserves):
            for other_role, other in reserves[i+1:]:
                if intersects(shape, other):
                    raise ValueError('Collection upgrade reservations overlap: '+role+' / '+other_role)
    for role, ids in result.get('rolePortNodes', {}).items():
        if role not in roles or not ids or any(node not in nodes for node in ids):
            raise ValueError('Unbound template entrance: '+role)
    # Only adapt the captured shared-port topology, not arbitrary depot layouts.
    ports = result.get('rolePortNodes', {})
    if 'road_depot' in roles and ports.get('road_depot') == ports.get('truck') and ports.get('truck'):
        if not result.get('planningAdaptation'):
            depot = roles['road_depot']
            a = math.radians(depot['relativeRotation'])
            depot['localPosition']['x'] -= math.sin(a)*20
            depot['localPosition']['y'] += math.cos(a)*20
            result['planningAdaptation'] = {'depotSetbackM': 20, 'basis': 'Huaihua native building-group previews; revalidate new terrain', 'nativeVerifiedHere': False}
        port = ports['truck'][0]
        targets = [r['position'+str(j)] for r in result['roads'] for j in (0, 1) if r['node'+str(j)] == port]
        if not targets or any(p != targets[0] for p in targets):
            raise ValueError('Shared frontage node ambiguous')
        depot = roles['road_depot'];a = math.radians(depot['relativeRotation']);p = depot['localPosition']
        result['planningLinks'] = [dict(role='road_depot', targetRole='truck',
            position0={'x':p['x']+math.sin(a)*20.25, 'y':p['y']-math.cos(a)*20.25},
            position1=copy.deepcopy(targets[0]),
            basis='Native default depot entrance offset estimate; bind actual external node after build')]
    return result


def validate_inputs(snapshot, details, capacity):
    if details['state']['player'] != snapshot['state']['player']:
        raise ValueError('Details belong to another player/session')
    expected = {i['id']: i for i in snapshot['map']['industries']}
    actual = {i['id']: i for i in details['industries']}
    if set(expected) != set(actual) or set(expected) != {i['id'] for i in capacity['industries']}:
        raise ValueError('Industry inventory differs; refresh snapshot/details/capacity together')
    for k, row in expected.items():
        if row['fileName'] != actual[k]['resource'] or any(abs(row['position'][a]-actual[k]['position'][a]) > .1 for a in ('x','y')):
            raise ValueError('Industry identity/position changed: '+str(k))
    towns = {t['id'] for t in snapshot['map']['towns']}
    if any(b['town'] not in towns for b in details['buildings']):
        raise ValueError('Building references another map town')


def layout_key(snapshot, details, templates):
    from planning_shared_hubs import POLICY_VERSION
    from tf3_mcp.flat_areas import POLICY_VERSION as TERRAIN_POLICY,DEFAULT_MAX_GRADE,DEFAULT_MAX_HEIGHT_RANGE,RESERVE_MARGIN_M
    # Production rates and demand values do not move facilities. Geometry, IDs,
    # road topology, ownership or template changes always invalidate this cache.
    structural = {'frozenNodes':sorted(details.get('frozenNodes', [])),
                  'buildings':sorted((b['id'],b['town']) for b in details['buildings']),
                  'industries':sorted((i['id'],i['construction']) for i in details['industries'])}
    terrain_policy=dict(version=TERRAIN_POLICY,maxGrade=DEFAULT_MAX_GRADE,maxHeightRangeM=DEFAULT_MAX_HEIGHT_RANGE,reserveMarginM=RESERVE_MARGIN_M)
    return digest({'snapshot':snapshot, 'structure':structural, 'templates':templates,'sharing_policy':POLICY_VERSION,'terrain_policy':terrain_policy})


def strip_native_evidence(value):
    if isinstance(value, list):
        return [strip_native_evidence(v) for v in value]
    if not isinstance(value, dict):
        return value
    removed = {'native_preview','native_building_group_preview','preview_token','previewToken'}
    out = {k:strip_native_evidence(v) for k,v in value.items() if k not in removed}
    for key in ('native_verified','nativeVerifiedHere','native_joint_road_preview'):
        if key in out:out[key] = False
    if out.get('status','').startswith('native_'):out['status'] = 'candidate_requires_fresh_native_preview'
    return out


def select_preview_rows(plan, section, owners=None, ids=None):
    facilities = plan['facilities']+plan.get('ports', [])
    fm = {f['id']:f for f in facilities}
    if section == 'groups':
        rows = [dict(id=h['owner'], facilities=[fm[f] for f in h['facilities'].values()]) for h in plan['hubs']]
    elif section == 'facilities':rows = facilities
    else:rows = plan.get('city_stops' if section=='stops' else section, [])
    if owners:
        requested = set(owners)
        known = {h['owner'] for h in plan['hubs']} | {f['owner'] for f in facilities if f.get('owner')}
        known |= {'P'+str(f['industry']) for f in plan.get('ports', [])}
        if requested-known:raise ValueError('Unknown owner: '+str(sorted(requested-known)))
        members = {v for h in plan['hubs'] if h['owner'] in requested for v in h['facilities'].values()}
        members |= {f['id'] for f in facilities if f.get('owner') in requested}
        members |= {f['id'] for f in plan.get('ports', []) if 'P'+str(f['industry']) in requested}
        road_ids = {v for h in plan['hubs'] if h['owner'] in requested for v in h['roads']}
        if section=='groups':rows=[r for r in rows if r['id'] in requested]
        elif section=='facilities':rows=[r for r in rows if r['id'] in members]
        elif section=='roads':rows=[r for r in rows if r['id'] in road_ids or r.get('from_facility') in members or r.get('to_facility') in members]
        else:rows=[r for r in rows if 'T'+str(r.get('town')) in requested]
    if ids:
        requested=set(ids);available={r['id'] for r in rows}
        if requested-available:raise ValueError('Unknown preview IDs: '+str(sorted(requested-available)))
        rows=[r for r in rows if r['id'] in requested]
    return rows
