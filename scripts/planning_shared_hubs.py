"""Offline city/industry sharing candidates; never native path or capacity clearance."""
import heapq
import math

POLICY_VERSION = 'city-production-under-3000-v1'

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
            if road is None:continue
            # Include both access legs. Nearest-node association still needs native validation.
            feeder = road+distance(p,nodes[near])+distance(nodes[h['node']],h['position'])
            seconds = feeder/11+90
            if seconds > distance(p,h['position'])/45+330:continue
            candidates.append(dict(hub_owner=h['owner'],city=h['entity'],center_distance_m=center,
                feeder_distance_m=feeder,feeder_seconds_estimate=seconds,
                native_path_verified=False,capacity_verified=False))
        if candidates:
            assignments[str(industry['id'])] = min(candidates,key=lambda c:(c['feeder_seconds_estimate'],c['hub_owner']))
    return assignments

def hub_owner(entity, is_industry, assignments):
    return assignments.get(str(entity),{}).get('hub_owner','I'+str(entity)) if is_industry else 'T'+str(entity)

def same_hub(a, b):
    return bool(a and b and a['owner']==b['owner'])
