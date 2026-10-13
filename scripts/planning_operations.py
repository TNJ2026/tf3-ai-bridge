"""Offline operating forecasts. Never grants native capability or build approval."""
import math
from collections import defaultdict


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def endpoint_key(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ('existing_industry', 'town'):
            if key in value:
                return key + ':' + str(value[key])
    raise ValueError('Unsupported transport endpoint')


def assign_air_maintenance(plan):
    """Prefer capable endpoint candidates, balance forecast fleets, then detour.

    A heliport is only a capability *candidate* without current readback. Explicit
    negative capability evidence excludes it; unknown capability stays pending.
    """
    facilities = {f['id']: f for f in plan['facilities'] + plan.get('ports', [])}
    candidates = [f for f in facilities.values() if f['kind'] == 'heliport'
                  and f.get('maintenance_capability_verified') is not False]
    loads = defaultdict(float)
    result = []
    for line in sorted((l for l in plan['line_specs'] if l['mode'] == 'HELICOPTER'),
                       key=lambda l: (-l.get('fleet_forecast', 1), l['id'])):
        ends = [facilities.get(endpoint_key(line[e]), line[e] if isinstance(line[e], dict) else {})
                for e in ('source', 'destination')]
        positions = [e.get('position') for e in ends]
        if not candidates or not all(positions):
            line['maintenance_base'] = None
            line['maintenance_assignment'] = {'status': 'unresolved', 'nativeVerified': False}
            result.append(dict(line=line['id'], **line['maintenance_assignment']))
            continue
        direct = math.dist([positions[0][a] for a in ('x', 'y')], [positions[1][a] for a in ('x', 'y')])
        def detour(f):
            return max(0., sum(math.dist([p[a] for a in ('x', 'y')], [f['position'][a] for a in ('x', 'y')]) for p in positions) - direct)
        local = [f for f in candidates if f['id'] in (line['source'], line['destination'])]
        # No unbounded balancing: remote candidates must be within 500m of the
        # least-detour candidate. This is a ranking allowance, not service range.
        pool = local or [f for f in candidates if detour(f) <= min(map(detour, candidates)) + 500]
        selected = min(pool, key=lambda f: (loads[f['id']], detour(f), f['id']))
        fleet = line.get('fleet_forecast', 1)
        if not positive(fleet):
            raise ValueError('Invalid fleet forecast: ' + line['id'])
        loads[selected['id']] += fleet
        line['maintenance_base'] = selected['id']
        line['maintenance_assignment'] = dict(status='candidate_pending_native_readback',
            nativeVerified=False, endpointBase=bool(local), detourEstimateM=detour(selected),
            requiredChecks=['maintenance capability', 'normal operation without native faults', 'maintenance load'])
        result.append(dict(line=line['id'], base=selected['id'], fleetForecast=fleet, **line['maintenance_assignment']))
    # Routes can split across bases: preserve an explicit list instead of an
    # obsolete arbitrary single maintenance reference.
    for route in plan.get('routes', []):
        for leg in route.get('transfer_chain', []):
            if leg['mode'] == 'HELICOPTER':
                bases = sorted({l['maintenance_base'] for l in plan['line_specs']
                                if route['id'] in l.get('flows', []) and l['mode'] == 'HELICOPTER' and l.get('maintenance_base')})
                leg['maintenance_bases'] = bases
                leg['maintenance_base'] = bases[0] if len(bases) == 1 else None
    return dict(assignments=result, fleetLoadByBase=dict(loads), nativeVerified=False)


def chain_forecasts(plan):
    results = []
    air_groups = {}
    for hub in plan.get('hubs', []):
        for role,fid in hub['facilities'].items():
            if role in ('heliport','helipad','helipad2'):air_groups[fid]=hub['facilities']['warehouse']
    for f in plan.get('facilities', []):
        if f['kind'] in ('heliport','helipad') and f.get('shared_warehouse'):air_groups[f['id']]=f['shared_warehouse']
    for port in plan.get('ports', []):
        for role in ('helipad','helipad2'):
            if port.get(role):air_groups[port[role]]=port['warehouse']
    for route in plan.get('routes', []):
        legs = []
        cargo = str(route['cargo'])
        deadlines = []
        for leg in route.get('transfer_chain', []):
            def match_key(e):
                key=endpoint_key(e)
                return air_groups.get(key,key) if leg['mode']=='HELICOPTER' else key
            sources = {match_key(leg['from'])}
            destinations = {match_key(leg['to'])}
            if leg.get('source_second'): sources.add(match_key(leg['source_second']))
            if leg.get('destination_second'): destinations.add(match_key(leg['destination_second']))
            lines = [l for l in plan['line_specs'] if route['id'] in l.get('flows', [])
                     and l['mode'] == leg['mode'] and match_key(l['source']) in sources
                     and match_key(l['destination']) in destinations and positive(l['cargos'].get(cargo))]
            if not lines or any(not positive(l.get(k)) for l in lines for k in ('oneway_seconds_forecast', 'headway_seconds_forecast')):
                legs.append(dict(mode=leg['mode'], status='missing_forecast')); continue
            total = sum(l['cargos'][cargo] for l in lines)
            # Parallel services are alternatives, never serial legs. Weight by
            # allocated cargo; conservative waiting assumes assigned service.
            travel = sum(l['oneway_seconds_forecast'] * l['cargos'][cargo] / total for l in lines)
            wait = sum(l['headway_seconds_forecast'] * .5 * l['cargos'][cargo] / total for l in lines)
            deadlines.extend(l['deadline_seconds'] for l in lines if positive(l.get('deadline_seconds')))
            legs.append(dict(mode=leg['mode'], lines=[l['id'] for l in lines], travelSeconds=travel, expectedWaitSeconds=wait))
        mapped = {i for leg in legs for i in leg.get('lines', [])}
        expected = {l['id'] for l in plan['line_specs'] if route['id'] in l.get('flows', []) and positive(l['cargos'].get(cargo))}
        unmapped = sorted(expected - mapped)
        complete = bool(legs) and not unmapped and all('travelSeconds' in l for l in legs)
        travel = sum(l['travelSeconds'] for l in legs) if complete else None
        estimate = sum(l['travelSeconds'] + l['expectedWaitSeconds'] for l in legs) if complete else None
        deadline = plan.get('cargo_deadlines_seconds', {}).get(cargo) or (min(deadlines) if deadlines else None)
        results.append(dict(route=route['id'], cargo=route['cargo'], legs=legs, complete=complete, unmappedLines=unmapped,
            travelSeconds=travel, estimatedTotalSeconds=estimate, deadlineSeconds=deadline,
            deadlineBasis='cargo' if cargo in plan.get('cargo_deadlines_seconds', {}) else 'conservative line minimum',
            riskForecast=estimate > deadline if complete and positive(deadline) else None,
            nativeTimingVerified=False, acceptanceGate=False, basis='travel + half headway per leg; parallel services weighted by cargo; loading not separately measured'))
    return results


def platform_forecasts(plan, dwell_seconds=60, *, detailed=True):
    if not positive(dwell_seconds): raise ValueError('Positive dwell assumption required')
    pads = defaultdict(list)
    for line in plan['line_specs']:
        if line['mode'] != 'HELICOPTER': continue
        for end in ('source', 'destination'):
            terminal = line.get(end + '_terminal_index')
            if not isinstance(terminal, int) or isinstance(terminal, bool) or terminal < 0:
                if detailed:
                    raise ValueError('Explicit landing terminal required: ' + line['id'])
                terminal = None  # Route draft; bind actual terminals before execution.
            pads[(endpoint_key(line[end]), terminal)].append(line)
    rows = []
    for (facility, terminal), lines in sorted(pads.items()):
        valid = detailed and all(positive(l.get('headway_seconds_forecast')) for l in lines)
        frequency = sum(3600 / l['headway_seconds_forecast'] for l in lines) if valid else None
        occupancy = frequency * dwell_seconds / 3600 if valid else None
        rows.append(dict(facility=facility, terminal=terminal, lines=[l['id'] for l in lines],
            lineLimitPassed=len(lines) <= 3 if terminal is not None else None,
            arrivalsPerHour=frequency, dwellAssumptionSeconds=dwell_seconds if detailed else None,
            occupancyEstimate=occupancy,
            forecastStatus='not_requested' if not detailed else 'estimated' if valid else 'unknown',
            capacityReviewRequired=(terminal is not None and len(lines) > 3) or (occupancy is not None and occupancy >= .7),
            acceptanceGate=False, nativeTerminalVerified=False, queueVerified=False, maintenanceOccupancyIncluded=False))
    return rows


def enrich(plan):
    mode = plan.get('operationsAnalysis', 'basic')
    if mode not in ('basic', 'detailed'):
        raise ValueError('operationsAnalysis must be basic or detailed')
    detailed = mode == 'detailed'
    if detailed:
        for line in plan['line_specs']:
            if positive(line.get('oneway_seconds_forecast')) and positive(line.get('fleet_forecast')):
                line.setdefault('roundtrip_seconds_forecast',2*line['oneway_seconds_forecast'])
                line.setdefault('headway_seconds_forecast',line['roundtrip_seconds_forecast']/line['fleet_forecast'])
    maintenance = assign_air_maintenance(plan)
    for hub in plan.get('hubs', []):
        f = hub['facilities']
        hub['sharedStockCheck'] = [v for k, v in f.items() if k in ('heliport', 'helipad', 'helipad2', 'truck')]
        hub['sharedWarehousePlan'] = dict(warehouse=f['warehouse'], cargoFacilities=hub['sharedStockCheck'], primaryStockList=None, inventoryVerified=False)
    for decision in plan.get('collection_quantity_decisions', {}).get('decisions', []):
        hub = next((h for h in plan['hubs'] if h['owner'] == decision['owner']), None)
        if not hub: continue
        members = set(hub['facilities'].values())
        routes = [r for r in plan.get('routes', []) if any(endpoint_key(l[e]) in members
                  for l in plan['line_specs'] if r['id'] in l.get('flows', []) for e in ('source', 'destination'))]
        decision['traffic'] = [dict(route=r['id'], annual=r.get('annual'), cargo=r['cargo']) for r in routes]
        decision['maintenanceLines'] = [l['id'] for l in plan['line_specs'] if l.get('maintenance_base') in members]
    plan['operations_review'] = dict(schema=2, mode=mode, maintenance=maintenance,
        chains=chain_forecasts(plan) if detailed else [],
        platforms=platform_forecasts(plan, detailed=detailed), operationalAccepted=False)
    return plan['operations_review']
