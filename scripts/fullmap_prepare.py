"""Offline road shortlist and dependency-aware execution order. Never calls game."""
from __future__ import annotations
import argparse,hashlib,json,math,time,sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server/src'))
from tf3_mcp.route_planner import Terrain,_curve,_unit
from tf3_mcp.site_planner import BoxIndex

class RoadSurvey:
 """One immutable snapshot per preparation run; no persistent entity cache."""
 def __init__(self,snapshot):
  self.terrain=Terrain(snapshot['grid']);self.spacing=snapshot['grid']['spacing']
  self.index=BoxIndex(snapshot['obstacles']);self.samples={};self.sample_calls=0;self.sample_hits=0
 def sample(self,x,y):
  key=(x,y)
  if key in self.samples:self.sample_hits+=1;return self.samples[key]
  value=self.terrain.sample(x,y);self.sample_calls+=1
  if len(self.samples)<100000:self.samples[key]=value
  return value
 def score(self,path,max_grade=.10,clearance=8):
  if not 2<=len(path)<=128:return {'rejected':'control_count'}
  if any(not math.isfinite(float(p[k]))for p in path for k in ('x','y')):return {'rejected':'invalid_coordinate'}
  length=0;climb=0;last=None;work=0
  for a,b in zip(path,path[1:]):
   distance=math.hypot(b['x']-a['x'],b['y']-a['y'])
   if distance<.01:continue
   n=max(1,math.ceil(distance/min(10,self.spacing/2)))
   if work+n>10000:return {'rejected':'sampling_budget'}
   work+=n;length+=distance
   for j in range(n+1):
    t=j/n;x=a['x']+(b['x']-a['x'])*t;y=a['y']+(b['y']-a['y'])*t
    try:z,water=self.sample(x,y)
    except ValueError:return {'rejected':'outside_snapshot'}
    if water:return {'rejected':'water_requires_separate_design'}
    if last:
     run=math.hypot(x-last[0],y-last[1]);rise=abs(z-last[2]);climb+=rise
     if run>.001 and rise/run>max_grade:return {'rejected':'terrain_grade_requires_design'}
    # Existing streets are obstacles too: a new intersection needs a separately
    # resolved native design. Only tolerate overlap close to route endpoints.
    endpoint=min(math.hypot(x-path[0]['x'],y-path[0]['y']),math.hypot(x-path[-1]['x'],y-path[-1]['y']))<20
    if not endpoint and self.index.blocked({'min':{'x':x-clearance,'y':y-clearance},'max':{'x':x+clearance,'y':y+clearance}}):return {'rejected':'obstacle_or_crossing'}
    last=(x,y,z)
  if length<.01:return {'rejected':'zero_length'}
  return {'length_m':round(length,2),'climb_m':round(climb,2),'score':length+5*climb,
          'native_verified':False,'endpointClearanceUnverified':True}

def candidates(road):
 original=road.get('path',[])
 if len(original)<2:return
 a,b=original[0],original[-1]
 yield 'straight',[a,b]
 yield 'surveyed',original
 dx,dy=b['x']-a['x'],b['y']-a['y'];u=_unit(dx,dy);distance=math.hypot(dx,dy)
 if distance<40:return
 for offset in (-min(100,distance/4),min(100,distance/4),-min(250,distance/2),min(250,distance/2)):
  mid=((a['x']+b['x'])/2-u[1]*offset,(a['y']+b['y'])/2+u[0]*offset)
  curve=_curve([(a['x'],a['y']),mid,(b['x'],b['y'])],u,u,step=max(10,distance/100))
  if curve:yield 'smooth_offset_'+str(round(offset,2)),[{'x':x,'y':y}for x,y in curve]

def shortlist(survey,road,limit=3,max_grade=.10):
 if not 1<=limit<=3:raise ValueError('native shortlist limit must be 1..3')
 rows=[];rejected=Counter();seen=set()
 for label,path in candidates(road):
  key=tuple((round(p['x'],3),round(p['y'],3))for p in path)
  if key in seen:continue
  seen.add(key);result=survey.score(path,max_grade)
  if 'rejected'in result:rejected[result['rejected']]+=1
  else:rows.append(dict(result,label=label,path=path))
 rows.sort(key=lambda r:r['score'])
 return {'id':road['id'],'candidates':rows[:limit],'rejections':dict(rejected),'tested':len(seen),
         'status':'native_preview_required'if rows else'needs_local_redesign',
         'maxNativePreviews':limit,'buildAuthorized':False}

def execution_order(jobs,batch_size=8):
 """Order ready jobs near the last job; preserve every declared dependency."""
 if not 1<=batch_size<=16:raise ValueError('batch_size must be 1..16')
 remaining={j['id']:j for j in jobs}
 if len(remaining)!=len(jobs):raise ValueError('duplicate job ID')
 ids=set(remaining)
 for j in jobs:
  if set(j.get('depends_on',[]))-ids:raise ValueError('unknown dependency: '+j['id'])
 done=set();ordered=[];last={'x':0,'y':0}
 while remaining:
  ready=[j for j in remaining.values()if set(j.get('depends_on',[]))<=done]
  if not ready:raise ValueError('dependency cycle')
  # Stage order does not grant authorization; lines/vehicles remain explicit.
  def rank(j):
   p=j.get('position')or last
   return (math.hypot(p.get('x',last['x'])-last['x'],p.get('y',last['y'])-last['y']),j['id'])
  j=min(ready,key=rank);ordered.append({'id':j['id'],'stage':j.get('stage'),'authorization':j.get('authorization'),'depends_on':j.get('depends_on',[])})
  last=j.get('position')or last;done.add(j['id']);del remaining[j['id']]
 return [ordered[i:i+batch_size]for i in range(0,len(ordered),batch_size)]

def prepare(plan,snapshot,manifest):
 def signature(rows,kind):
  return sorted((r['name']if kind=='town'else r.get('resource',r.get('fileName')),round(r['position']['x'],2),round(r['position']['y'],2))for r in rows)
 if signature(plan['cities'],'town')!=signature(snapshot['map']['towns'],'town')or signature(plan['industries'],'industry')!=signature(snapshot['map']['industries'],'industry'):
  raise ValueError('Snapshot belongs to a different map; acquire matching inputs')
 if plan['session']['player']!=snapshot['state']['player']:raise ValueError('Snapshot player does not match plan')
 started=time.perf_counter();survey=RoadSurvey(snapshot)
 roads=[shortlist(survey,r)for r in plan['roads']]
 return {'schema':1,'mode':'offline_preparation_only','roads':roads,'batches':execution_order(manifest['jobs']),
         'snapshotState':snapshot.get('state'),'snapshotRevisions':snapshot.get('revisions'),
         'limitations':['Terrain interpolation is approximate; grade threshold is a screening preference, not an engine limit.',
          'Endpoints, tangents, slopes, upgrade space, native collisions and reputation require current-game verification.',
          'Do not execute this schedule as authorization. Reload/change/mutation requires fresh local survey and native preview.'],
         'performance':{'seconds':time.perf_counter()-started,'terrainSamples':survey.sample_calls,'sampleCacheHits':survey.sample_hits,'obstacleChecks':survey.index.checks}}

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for key in ('plan','snapshot','manifest','output'):ap.add_argument('--'+key,type=Path,required=True)
 a=ap.parse_args();files={k:getattr(a,k).read_bytes()for k in ('plan','snapshot','manifest')}
 result=prepare(*(json.loads(files[k])for k in ('plan','snapshot','manifest')))
 result['inputDigests']={k:hashlib.sha256(v).hexdigest()for k,v in files.items()}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'roads':len(result['roads']),'shortlisted':sum(bool(r['candidates'])for r in result['roads']),'batches':len(result['batches']),'performance':result['performance']}))
if __name__=='__main__':main()
