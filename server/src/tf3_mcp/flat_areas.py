"""Offline sampled flat-ground regions and footprint checks; never build approvals."""
from __future__ import annotations

import hashlib
import json
import math
from collections import deque

from .development_planner import grid_bounds, number, validate_snapshot

POLICY_VERSION = 'flat-ground-city-service-balanced-v2'
DEFAULT_MAX_GRADE = .05
DEFAULT_MAX_HEIGHT_RANGE = 5.0
RESERVE_MARGIN_M = 20.0  # Planning allowance, not a verified native upgrade size.


def grid_digest(grid):
    return hashlib.sha256(json.dumps(grid, sort_keys=True, allow_nan=False).encode('utf8')).hexdigest()


def preference_key(profile, access_profile, distance):
    """Flat collection AND access first; distance only breaks terrain ties."""
    available = not profile['outsideSurvey'] and profile['dry']
    access_available = not access_profile['outsideSurvey'] and access_profile['dry']
    flat = available and access_available and profile['flatPreferred'] and access_profile['maxGroundGrade'] <= DEFAULT_MAX_GRADE
    return (not flat, not (available and access_available),
            max(profile['maxGroundGrade'] or 0, access_profile['maxGroundGrade'] or 0),
            profile['heightRangeM'] if available else math.inf, distance)


def city_preference_key(profile, access_profile, service_distance):
    """Non-monetary heuristic: small terrain improvements cannot dominate distance.

    Native safety, setbacks and collision checks remain separate hard gates.
    The score is an estimated distance equivalent, not a construction cost.
    """
    unavailable = any(p['outsideSurvey'] or not p['dry'] for p in (profile, access_profile))
    grade = max(p['maxGroundGrade'] or 0 for p in (profile, access_profile))
    height = max(p['heightRangeM'] or 0 for p in (profile, access_profile))
    return (unavailable, service_distance + 10000*max(0, grade-.05) + 30*height,
            service_distance, grade, height)


class FlatTerrain:
    def __init__(self, grid, max_grade=DEFAULT_MAX_GRADE):
        validate_snapshot(dict(grid=grid))
        number(max_grade, 'flat max_grade', .001)
        if max_grade > 1:
            raise ValueError('flat max_grade must be <= 1')
        if any(type(w) is not bool for w in grid['water']):
            raise ValueError('water samples must be booleans')
        self.grid, self.max_grade = grid, max_grade
        self.nx, self.ny = grid['nx']-1, grid['ny']-1
        self.cells, self.cache = [], {}
        for j in range(self.ny):
            for i in range(self.nx):
                ids = (j*grid['nx']+i, j*grid['nx']+i+1,
                       (j+1)*grid['nx']+i, (j+1)*grid['nx']+i+1)
                z = [grid['heights'][k] for k in ids]
                # A bilinear surface's largest sampled gradient occurs at a corner.
                grade = max(math.hypot(z[a]-z[b], z[a]-z[c])/grid['spacing']
                            for a,b,c in ((0,1,2),(1,0,3),(2,3,0),(3,2,1)))
                dry = not any(grid['water'][k] for k in ids)
                self.cells.append(dict(dry=dry, grade=grade, lo=min(z), hi=max(z),
                                       flat=dry and grade <= max_grade))

    def profile(self, bounds, max_height_range=DEFAULT_MAX_HEIGHT_RANGE):
        """Checks every supporting grid cell; rectangular bounds may be conservative."""
        number(max_height_range, 'flat max_height_range')
        g = self.grid; surveyed = grid_bounds(g)
        for axis in ('x','y'):
            number(bounds['min'][axis], 'profile minimum', -1e9)
            number(bounds['max'][axis], 'profile maximum', -1e9)
            if bounds['min'][axis] > bounds['max'][axis]:
                raise ValueError('inverted profile bounds')
        if any(bounds['min'][a] < surveyed['min'][a] or bounds['max'][a] > surveyed['max'][a] for a in ('x','y')):
            return dict(outsideSurvey=True, dry=False, flatPreferred=False, maxGroundGrade=None,
                        heightRangeM=None, sampledHeightRange=None, checkedCells=0)
        x0,y0 = (max(0,min(n-1,math.floor((bounds['min'][a]-g[a])/g['spacing'])))
                 for a,n in (('x',self.nx),('y',self.ny)))
        x1,y1 = (max(lo,min(n-1,math.ceil((bounds['max'][a]-g[a])/g['spacing'])-1))
                 for a,n,lo in (('x',self.nx,x0),('y',self.ny,y0)))
        key = (x0,y0,x1,y1)
        if key not in self.cache:
            cells = [self.cells[j*self.nx+i] for j in range(y0,y1+1) for i in range(x0,x1+1)]
            lo,hi = min(c['lo'] for c in cells),max(c['hi'] for c in cells)
            self.cache[key] = dict(outsideSurvey=False, dry=all(c['dry'] for c in cells),
                maxGroundGrade=max(c['grade'] for c in cells), heightRangeM=hi-lo,
                sampledHeightRange=[lo,hi], checkedCells=len(cells))
        p = dict(self.cache[key])
        p['flatPreferred'] = p['dry'] and p['maxGroundGrade'] <= self.max_grade and p['heightRangeM'] <= max_height_range
        return p

    def regions(self):
        visited=set(); regions=[];g=self.grid
        for start,c in enumerate(self.cells):
            if not c['flat'] or start in visited:
                continue
            todo=deque([start]);visited.add(start);members=[]
            while todo:
                k=todo.popleft();members.append(k);x,y=k%self.nx,k//self.nx
                adjacent=[]
                if x:adjacent.append(k-1)
                if x+1<self.nx:adjacent.append(k+1)
                if y:adjacent.append(k-self.nx)
                if y+1<self.ny:adjacent.append(k+self.nx)
                for n in adjacent:
                    if n not in visited and self.cells[n]['flat']:
                        visited.add(n);todo.append(n)
            # Exact cell runs preserve water/steep holes inside each region's bounding box.
            runs=[]
            for k in sorted(members):
                x,y=k%self.nx,k//self.nx
                if runs and runs[-1][0]==y and runs[-1][2]==x:runs[-1][2]=x+1
                else:runs.append([y,x,x+1])
            x0,x1=min(r[1]for r in runs),max(r[2]for r in runs)
            y0,y1=min(r[0]for r in runs),max(r[0]for r in runs)+1
            regions.append(dict(id='F'+str(len(regions)+1),cells=len(members),
                areaM2=len(members)*g['spacing']**2,cellRuns=runs,
                bounds=dict(min=dict(x=g['x']+x0*g['spacing'],y=g['y']+y0*g['spacing']),
                            max=dict(x=g['x']+x1*g['spacing'],y=g['y']+y1*g['spacing'])),
                maxGroundGrade=max(self.cells[k]['grade']for k in members),
                sampledHeightRange=[min(self.cells[k]['lo']for k in members),max(self.cells[k]['hi']for k in members)]))
        return sorted(regions,key=lambda r:(-r['areaM2'],r['id']))

    def report(self):
        g=self.grid;regions=self.regions()
        return dict(schema=1,policy=POLICY_VERSION,gridDigest=grid_digest(g),
            grid={k:g[k]for k in ('x','y','nx','ny','spacing')},bounds=grid_bounds(g),regions=regions,
            screening=dict(maxGroundGrade=self.max_grade,collectionMaxHeightRangeM=DEFAULT_MAX_HEIGHT_RANGE,
                upgradeMarginM=RESERVE_MARGIN_M,basis='planning heuristics, not native construction limits'),
            summary=dict(regions=len(regions),flatCells=sum(r['cells']for r in regions),
                totalCells=len(self.cells),areaM2=sum(r['areaM2']for r in regions)),
            refinement=dict(recommendedLocalSpacingM=25,requiredBeforeNativePreview=g['spacing']>25),
            sampledOnly=True,buildable=None,requiresNativePreview=True,gameCalls=0,
            warnings=['Regions describe terrain only; obstacles, retreat distance, cargo coverage and access need separate checks.',
                      'Cell runs are the region mask; bounding boxes may contain water or steep holes.',
                      'Coarse sampling can miss small ridges and port-height differences.'])


def svg_layer(report):
    """Standalone terrain layer; no UI or planning card is opened."""
    g=report['grid'];step=g['spacing'];width=(g['nx']-1)*step;height=(g['ny']-1)*step
    shapes=[]
    for region in report['regions']:
        for row,start,end in region['cellRuns']:
            shapes.append(f'<rect x="{start*step:g}" y="{height-(row+1)*step:g}" width="{(end-start)*step:g}" height="{step:g}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}"><title>Sampled flat terrain; native preview required</title><g fill="#6abf8a" fill-opacity="0.65">'+''.join(shapes)+'</g></svg>'
