"""Straight corridor -> town/building detour -> terrain/crossing profile -> smoothing checks."""
import heapq
import math
import time
from collections import Counter
from .route_planner import Terrain, Obstacles, _curve, _unit


def town_regions(rows,buffer=120):
    regions={}
    for r in rows:
        if r.get('town') is None:continue
        key=str(r['town']);lo,hi=r['min'],r['max']
        if key not in regions:regions[key]=[lo['x'],lo['y'],hi['x'],hi['y']]
        else:
            b=regions[key];b[:]=[min(b[0],lo['x']),min(b[1],lo['y']),max(b[2],hi['x']),max(b[3],hi['y'])]
    return [dict(entity='town:'+k,kind='TOWN_REGION',min=dict(x=b[0]-buffer,y=b[1]-buffer,z=0),
                 max=dict(x=b[2]+buffer,y=b[3]+buffer,z=0)) for k,b in regions.items()]


def inside(p,r,pad=0):
    return r['min']['x']-pad<=p[0]<=r['max']['x']+pad and r['min']['y']-pad<=p[1]<=r['max']['y']+pad


def segment_points(a,b,step=15):
    n=max(1,math.ceil(math.dist(a,b)/step))
    return [(a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n) for i in range(n+1)]


def detour(start,end,buildings,towns,grid,terrain=None):
    """A* only when the straight line hits an obstacle. End towns allow entry/exit."""
    endpoint_towns=[r for r in towns if inside(start,r) or inside(end,r)]
    hard_towns=[r for r in towns if r not in endpoint_towns]
    index=Obstacles(buildings+hard_towns)
    def clear(a,b):return not any(any(index.conflicts(x,y,0)) for x,y in segment_points(a,b))
    if terrain is None and clear(start,end):return [start,end]
    step=max(50,grid['spacing']);origin=(grid['x'],grid['y'])
    def cell(p):return (round((p[0]-origin[0])/step),round((p[1]-origin[1])/step))
    def point(c):return (origin[0]+c[0]*step,origin[1]+c[1]*step)
    s,t=cell(start),cell(end);pq=[(0,0,s)];cost={s:0};parent={};closed=set()
    # Connect exact endpoints to lattice using collision checked connectors.
    if not clear(start,point(s)) or not clear(point(t),end):return None
    while pq and len(closed)<100000:
        _,g,u=heapq.heappop(pq)
        if u in closed:continue
        if u==t:
            cells=[u]
            while cells[-1]!=s:cells.append(parent[cells[-1]])
            path=[start]+[point(c) for c in reversed(cells)]+[end]
            def travel(a,b):
                if terrain is None:return math.dist(a,b)
                pts=segment_points(a,b,50);value=0
                for p,q in zip(pts,pts[1:]):
                    h0,_=terrain.sample(*p);h,w=terrain.sample(*q)
                    value+=math.dist(p,q)*(2 if w else 1)+2*abs(h-h0)
                return value
            prefix=[0.]
            for a,b in zip(path,path[1:]):prefix.append(prefix[-1]+travel(a,b))
            reduced=[path[0]];i=0
            while i<len(path)-1:
                j=len(path)-1
                while j>i+1 and (not clear(path[i],path[j]) or
                        (terrain is not None and travel(path[i],path[j])>(prefix[j]-prefix[i])*1.05)):
                    j-=1
                if math.dist(reduced[-1],path[j])>.1:reduced.append(path[j])
                i=j
            return reduced
        closed.add(u)
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            v=(u[0]+dx,u[1]+dy);p,q=point(u),point(v)
            if not (0<=v[0]*step<=(grid['nx']-1)*grid['spacing'] and 0<=v[1]*step<=(grid['ny']-1)*grid['spacing']):continue
            if not clear(p,q):continue
            d=math.dist(p,q);penalty=0
            if terrain:
                h,w=terrain.sample(*q);h0,_=terrain.sample(*p)
                penalty=abs(h-h0)*2+(d if w else 0)
            ng=g+d+penalty
            if ng<cost.get(v,float('inf')):
                cost[v]=ng;parent[v]=u;heapq.heappush(pq,(ng+math.dist(q,end),ng,v))
    return None


def profile(xy,ground,roads,start_z,end_z,grade,mode):
    """Propagate height constraints both ways to reserve ramp distance before crossings."""
    distance=[0.]
    for a,b in zip(xy,xy[1:]):distance.append(distance[-1]+math.dist(a,b))
    n=len(xy);lo=[-1e4]*n;hi=[1e4]*n;road_index=Obstacles(roads)
    crossings=[]
    for i,((x,y),(h,water)) in enumerate(zip(xy,ground)):
        if water:lo[i]=max(lo[i],5.)
        for k in road_index.buckets.get((math.floor(x/100),math.floor(y/100)),()):
            r=roads[k]
            if inside((x,y),r,20):
                crossings.append(r['entity'])
                if mode=='over':lo[i]=max(lo[i],r['max']['z']+10)
                else:hi[i]=min(hi[i],r['min']['z']-10)
    if not lo[0]<=start_z<=hi[0] or not lo[-1]<=end_z<=hi[-1]:return None
    lo[0]=hi[0]=start_z;lo[-1]=hi[-1]=end_z
    for indices in (range(1,n),range(n-2,-1,-1)):
        for i in indices:
            j=i-1 if isinstance(indices,range) and indices.step==1 else i+1
            allowance=abs(distance[i]-distance[j])*grade
            lo[i]=max(lo[i],lo[j]-allowance);hi[i]=min(hi[i],hi[j]+allowance)
    if any(a>b+1e-7 for a,b in zip(lo,hi)):return None
    zs=[start_z]
    for i in range(1,n):
        allowance=(distance[i]-distance[i-1])*grade
        low=max(lo[i],zs[-1]-allowance);high=min(hi[i],zs[-1]+allowance)
        if low>high+1e-7:return None
        zs.append(min(high,max(low,ground[i][0])))
    return zs,distance,sorted(set(crossings))


def plan_staged(snapshot,max_candidates=3,max_grade=.025,min_radius=120):
    if not 1<=max_candidates<=10:raise ValueError('max_candidates must be 1..10')
    began=time.perf_counter();grid=snapshot['grid'];terrain=Terrain(grid)
    buildings=[r for r in snapshot['obstacles'] if r['kind']!='BASE_EDGE']
    roads=[r for r in snapshot['obstacles'] if r['kind']=='BASE_EDGE']
    towns=town_regions(buildings)
    candidates=[];reject=Counter();straight=[];attempts=0
    for a in snapshot['stations'][0]['ports']:
        for b in snapshot['stations'][1]['ports']:
            start=(a['position']['x'],a['position']['y']);end=(b['position']['x'],b['position']['y'])
            straight.append(dict(startNode=a['node'],endNode=b['node'],length=round(math.dist(start,end),1)))
            da=_unit(a['direction']['x'],a['direction']['y']);db=_unit(b['direction']['x'],b['direction']['y'])
            # Short station stubs, followed by free detour waypoints.
            stub=min(200,math.dist(start,end)/5)
            sa=(start[0]+da[0]*stub,start[1]+da[1]*stub);sb=(end[0]+db[0]*stub,end[1]+db[1]*stub)
            port_buildings=[r for r in buildings if not inside(start,r,20) and not inside(end,r,20)]
            for terrain_feedback in (False,True):
                line=detour(sa,sb,port_buildings,[r for r in towns if not inside(start,r) and not inside(end,r)],grid,terrain if terrain_feedback else None)
                if not line:reject['no_detour']+=1;continue
                anchors=[start]+line+[end]
                xy=_curve(anchors,da,(-db[0],-db[1]),step=15)
                if len(xy)<3:reject['geometry']+=1;continue
                protected=Obstacles(port_buildings+[r for r in towns if not inside(start,r) and not inside(end,r)])
                if any(any(protected.conflicts(x,y,0)) for x,y in xy):reject['smoothing_collision']+=1;continue
                radii=[]
                for p,q,r in zip(xy,xy[1:],xy[2:]):
                    area=abs((q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]))
                    if area>1e-7:radii.append(math.dist(p,q)*math.dist(q,r)*math.dist(p,r)/(2*area))
                if min(radii,default=1e9)<min_radius:reject['curve_radius']+=1;continue
                try:ground=[terrain.sample(x,y) for x,y in xy]
                except ValueError:reject['outside_snapshot']+=1;continue
                for mode in ('over','under'):
                    attempts+=1
                    result=profile(xy,ground,roads,a['position']['z'],b['position']['z'],max_grade,mode)
                    if result is None:reject['crossing_grade']+=1;continue
                    zs,dist,crossings=result;path=[];bridge=tunnel=0
                    for i,((x,y),z,(h,w)) in enumerate(zip(xy,zs,ground)):
                        typ='bridge' if w or z-h>7 else 'tunnel' if h-z>7 else 'ground'
                        d=dist[i]-dist[i-1] if i else 0
                        if typ=='bridge':bridge+=d
                        if typ=='tunnel':tunnel+=d
                        path.append(dict(x=x,y=y,z=z,h=h,water=w,structure=typ))
                    candidates.append(dict(startNode=a['node'],endNode=b['node'],path=path,via=[dict(x=x,y=y) for x,y in anchors],
                        length=round(dist[-1],1),bridgeLength=round(bridge,1),tunnelLength=round(tunnel,1),
                        score=round(dist[-1]+bridge*1.5+tunnel*2,1),crossings=crossings,crossingMode=mode,
                        minSampledRadius=round(min(radii,default=1e9),1),
                        maxSampledGrade=max((abs(zs[i]-zs[i-1])/(dist[i]-dist[i-1]) for i in range(1,len(zs)) if dist[i]>dist[i-1]),default=0),requiresNativePreview=True))
                if any(c['startNode']==a['node'] and c['endNode']==b['node'] for c in candidates):break
    candidates.sort(key=lambda c:c['score']);unique=[];seen=set()
    for c in candidates:
        key=(c['startNode'],c['endNode'],c['crossingMode'],c['length'])
        if key not in seen:unique.append(c);seen.add(key)
    return dict(candidates=unique[:max_candidates],buildable=None,requiresNativePreview=True,
                stages=['straight','town_and_building_detour','terrain_and_road_crossings','smoothing_validation'],
                straightRoutes=straight,townRegions=towns,
                stats=dict(localSeconds=round(time.perf_counter()-began,4),evaluated=attempts,rejected=dict(reject),
                           townRegions=len(towns),obstacles=len(snapshot['obstacles'])),
                limitation='Sampled terrain and conservative bounds; native preview required. Polling cache may lag manual edits.')
