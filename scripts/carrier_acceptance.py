"""Shared commissioning policy; quantities, return trips and forecasts are not gates."""
import math


def policy():
    return dict(version='departure-only-20261012',
        scope=['ROAD','RAIL','TRAM','WATER','AIR'],
        required=['actual departure from base','normal assigned-line operation','no native line/path fault'],
        returnTripRequired=False, passengerCountsRequired=False, cargoDeliveryCountsRequired=False,
        forecastsAreAcceptanceGates=False, monitoringScope='account_only', cashFloor=1500000)


def departure_result(snapshot, expected, previous=None):
    """expected is vehicle->line. Missing evidence never becomes success."""
    rows={v['id']:v for v in snapshot.get('vehicles',[])}
    old={v['id']:v for v in (previous or {}).get('vehicles',[])}
    statuses={}
    fault_lines=set()
    unknown_problem=False
    for problem in snapshot.get('problems',[]):
        ident=problem if type(problem) is int else next((problem[k] for k in ('line','lineId','entity','id') if k in problem),None) if isinstance(problem,dict) else None
        if type(ident) is int: fault_lines.add(ident)
        else: unknown_problem=True
    for ident,line in expected.items():
        v=rows.get(ident)
        if not v:
            statuses[ident]='missing';continue
        if v.get('line')!=line:
            statuses[ident]='wrong_line';continue
        if v.get('noPath') is True or line in fault_lines:
            statuses[ident]='native_fault';continue
        if v.get('noPath') is not False or v.get('userStopped') is not False or unknown_problem:
            statuses[ident]='unknown_or_stopped';continue
        m=v.get('motion',{})
        available=m.get('groundAvailable') is True or m.get('aircraftAvailable') is True
        speeds=[m.get('ground',{}).get('dyn',{}).get('speed'),m.get('aircraft',{}).get('speed')]
        moving=any(type(s) in (int,float) and math.isfinite(s) and abs(s)>0 for s in speeds)
        p,q=m.get('position',{}),old.get(ident,{}).get('motion',{}).get('position',{})
        if all(type(t.get(k)) in (int,float) and math.isfinite(t[k]) for t in (p,q) for k in ('x','y','z')):
            moving=moving or math.dist([p[k] for k in ('x','y','z')],[q[k] for k in ('x','y','z')])>0
        statuses[ident]='accepted' if available and moving else 'departure_pending'
    return dict(accepted=bool(expected) and all(s=='accepted' for s in statuses.values()),vehicles=statuses)


def nearest_order(stops):
    """Deterministic quadratic heuristic, not an exhaustive shortest-tour solver."""
    if not stops:return []
    ordered=[stops[0]];remaining=list(stops[1:])
    while remaining:
        p=ordered[-1]['position']
        nxt=min(remaining,key=lambda s:((s['position']['x']-p['x'])**2+(s['position']['y']-p['y'])**2,str(s['id'])))
        ordered.append(nxt);remaining.remove(nxt)
    return ordered
