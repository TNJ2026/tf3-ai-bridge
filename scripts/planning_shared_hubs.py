"""Offline city/industry sharing candidates; never native path or capacity clearance."""
import heapq
import math

POLICY_VERSION = 'demand-sized-land-city-coordination-v3'

def distance(a, b):
    return math.hypot(a['x']-b['x'], a['y']-b['y'])

def select_shared_hubs(snapshot, hubs):
    from tf3_mcp.site_planner import curve
    nodes, graph = {}, {}
    for edge in snapshot['obstacles']:
        if edge['kind'] != 'BASE_EDGE':
            continue
        a, b = edge['node0'], edge['node1']
        nodes[a], nodes[b] = edge['position0'], edge['position1']
        points = [curve(edge, k/8) for k in range(9)]
        length = sum(math.dist(p, q) for p, q in zip(points, points[1:]))
        graph.setdefault(a, []).append((b, length))
        graph.setdefault(b, []).append((a, length))
    towns = {t['id']:t for t in snapshot['map']['towns']}
    cities = [h for h in hubs if h['kind']=='city' and h['node'] in nodes]
    retained = {h['entity'] for h in hubs if h['kind']=='production'}
    paths = {}
    for h in cities:
        start = h['node']; ds = {start:0}; queue = [(0, start)]
        while queue:
            length, node = heapq.heappop(queue)
            if length != ds[node]:continue
            for neighbor, cost in graph.get(node, []):
                value = length+cost
                if value < ds.get(neighbor, math.inf):
                    ds[neighbor] = value; heapq.heappush(queue, (value, neighbor))
        paths[h['owner']] = ds
    strict = snapshot.get('planning_policy',{}).get('strict_city_sharing_under_3000',False)
    assignments = {}
    for industry in snapshot['map']['industries']:
        if not nodes or industry['id'] in retained or any(k in industry['fileName'] for k in ('oil_platform','fishing_grounds')):
            continue
        p = industry['position']; near = min(nodes, key=lambda n:distance(p,nodes[n]))
        candidates = []
        for h in cities:
            center = distance(p, towns[h['entity']]['position'])
            if center >= 3000:continue
            road = paths[h['owner']].get(near)
            if road is None and not strict:continue
            # Include both access legs. Nearest-node association still needs native validation.
            feeder = (road if road is not None else distance(nodes[near],nodes[h['node']]))+distance(p,nodes[near])+distance(nodes[h['node']],h['position'])
            seconds = feeder/11+90
            if not strict and seconds > distance(p,h['position'])/45+330:continue
            candidates.append(dict(hub_owner=h['owner'],city=h['entity'],center_distance_m=center,
                feeder_distance_m=feeder,feeder_seconds_estimate=seconds,
                native_path_verified=False,capacity_verified=False,road_connection_required=road is None,strict_distance_policy=strict))
        if candidates:
            assignments[str(industry['id'])] = min(candidates,key=lambda c:(c['feeder_seconds_estimate'],c['hub_owner']))
    return assignments

def hub_owner(entity, is_industry, assignments):
    return assignments.get(str(entity),{}).get('hub_owner','I'+str(entity)) if is_industry else 'T'+str(entity)

def same_hub(a, b):
    return bool(a and b and a['owner']==b['owner'])


def city_siting_reviews(hubs, cities):
    """Flag overlapping service choices; proximity never automatically merges hubs.

    1000m and 1.25 are conservative review triggers, not minimum separation,
    warehouse coverage, or evidence of actual road/capacity feasibility.
    """
    towns={t['id']:t for t in cities}
    rows=sorted((h for h in hubs if h['kind']=='city'),key=lambda h:h['owner'])
    reviews=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            gap=distance(a['position'],b['position'])
            service=[]
            for own,other in ((a,b),(b,a)):
                town=towns[own['entity']]['position']
                current=distance(town,own['position']);alternative=distance(town,other['position'])
                service.append(dict(city=own['entity'],current_owner=own['owner'],alternative_owner=other['owner'],
                    direct_distance_m=current,alternative_direct_distance_m=alternative,
                    road_distance_m=None,round_trip_seconds=None))
            if gap>1000 and not any(s['alternative_direct_distance_m']<=s['direct_distance_m']*1.25 for s in service):continue
            reviews.append(dict(owners=[a['owner'],b['owner']],anchor_distance_m=gap,
                triggers=dict(nearby=gap<=1000,potential_service_overlap=any(s['alternative_direct_distance_m']<=s['direct_distance_m']*1.25 for s in service)),
                service=service,status='pending_comparison',build_ready=False,
                alternatives=['share_one_collection','retain_separate_collections','relocate_nearer_served_city'],
                required_checks=['actual round-trip road travel and delivery coverage for both cities',
                    'aggregate cargo and passenger throughput; distinct terminals; stock counted once',
                    'upgrade space, noise, pollution and city growth',
                    'nearer site with limited grading versus distant flatter site',
                    'reuse existing facilities; no automatic demolition'],
                note='Screening only; record selected alternative and evidence before construction.'))
    return reviews


def shared_fishing_port(industry, ports, industries, waterpath, annual, capacity_limit=None):
    """Pair at most two fields; coarse water routes are candidates, never clearance."""
    if capacity_limit is not None and (not math.isfinite(capacity_limit) or capacity_limit<=0):
        raise ValueError('Fishing port annual handling budget must be positive')
    options=[]
    for port in ports:
        members=port.get('service_industries',[port['industry']])
        if len(members)!=1:continue  # no transitive A-B-C grouping
        first=industries[members[0]]
        if distance(first['position'],industry['position'])>3000:continue
        total=port.get('annual_forecast',0)+annual
        if capacity_limit is not None and total>capacity_limit:continue
        outbound=waterpath(industry['position'],port['position'])
        inbound=waterpath(port['position'],industry['position'])
        if not outbound or not inbound:continue
        length=sum(distance(a,b)for a,b in zip(outbound,outbound[1:]))
        return_length=sum(distance(a,b)for a,b in zip(inbound,inbound[1:]))
        # Avoid a geographically near pair whose actual sampled waterway detours.
        direct=distance(industry['position'],port['position'])
        if max(length,return_length)>direct*1.5+500:continue
        options.append((length,port['id'],port,outbound,inbound))
    if not options:return None
    _,_,port,outbound,inbound=min(options,key=lambda x:x[:2])
    return dict(port=port,outbound=outbound,inbound=inbound)


def validate_fishing_assignments(ports, industries):
    assigned={}
    for p in ports:
        members=p.get('service_industries',[p['industry']])
        if not members or len(members)>2 or len(set(members))!=len(members):
            raise ValueError('Fishing port requires one or two distinct fields')
        if p['industry'] not in members or any(i not in industries for i in members):
            raise ValueError('Fishing port has missing or inconsistent primary field')
        if len(members)==2 and distance(industries[members[0]]['position'],industries[members[1]]['position'])>3000:
            raise ValueError('Shared fishing fields exceed 3000m')
        for entity in members:
            if entity in assigned:raise ValueError('Fishing field assigned to multiple ports')
            if 'fishing_grounds' not in industries[entity]['resource']:raise ValueError('Non-fishing industry in port group')
            assigned[entity]=p
    return assigned


def finalize_land_quantities(hubs, facilities, roads, routes, cities, industries):
    """Only actual planned transfer/service references require a new full collection.

    Does not delete anything from the game. Explicit existing/built groups are
    retained, even when no current forecast uses them.
    """
    used=set()
    for route in routes:
        for leg in route['transfer_chain']:
            for k in ('from','to','warehouse','source_second','destination_second','maintenance_base'):
                if isinstance(leg.get(k),str):used.add(leg[k])
    keep={};decisions=[];removed=set()
    for owner,h in hubs.items():
        members=set(h['facilities'].values());required=bool(members&used)
        existing=h.get('existing',False) or h.get('built',False)
        if required or existing:keep[owner]=h
        else:removed.update(members)
        traffic=[dict(route=r['id'],annual=r.get('annual'),cargo=r.get('cargo')) for r in routes
                 if any(any(leg.get(k) in members for k in ('warehouse','source_second','destination_second','maintenance_base') if isinstance(leg.get(k),str))
                        or any(leg.get(k) in members for k in ('from','to') if isinstance(leg.get(k),str)) for leg in r['transfer_chain'])]
        decisions.append(dict(owner=owner,entity=h['entity'],kind=h['kind'],traffic=traffic,
            decision='retain_existing' if existing else 'required_by_transport' if required else 'omit_unused_candidate',
            reason='Actual transfer/service endpoints' if required else 'No current forecast requires this full collection; direct road service or unmet demand remains explicit',
            capacity_verified=False,requires_capacity_review=required))
    fs=[f for f in facilities if f['id']not in removed]
    rs=[r for r in roads if r.get('to_facility')not in removed and r.get('from_facility')not in removed and not removed.intersection(r.get('depends_on',[]))]
    service=[]
    for kind,rows in [('city',cities),('production',industries)]:
        for row in rows:
            movements=[r['id'] for r in routes if row['id'] in (r['source'],r['destination'])]
            service.append(dict(kind=kind,entity=row['id'],routes=movements,
                status='planned_transport' if movements else 'no_allocated_flow_requires_demand_review'))
    return keep,fs,rs,dict(policy=POLICY_VERSION,decisions=decisions,service_inventory=service,
        new_land_collections=sum(not(h.get('existing')or h.get('built'))for h in keep.values()),
        removed_candidate_owners=[r['owner']for r in decisions if r['decision']=='omit_unused_candidate'],
        native_capacity_verified=False)
