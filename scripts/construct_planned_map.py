"""Template-selected road-first or joint construction; no automatic sequential fallback."""
import argparse,json,subprocess,sys,time
from pathlib import Path
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--owners');ap.add_argument('--authorize-build',action='store_true');ap.add_argument('--mode',choices=['auto','road-first','joint','sequential'],default='auto');ap.add_argument('--isolated-test-save',action='store_true');ap.add_argument('--current-map-test',action='store_true');ap.add_argument('--defer-walking',action='store_true');a=ap.parse_args();
 if not a.authorize_build:ap.error('Planning pack only; explicit future build authorization required (--authorize-build)')
 p=json.loads(a.plan.read_text('utf8'));a.output.mkdir(parents=True,exist_ok=True)
 journal=a.output/'construction_run.json';v=json.loads(journal.read_text('utf8'))if journal.exists()else dict(started=time.time(),events=[],scope='facilities_roads_stops_only')
 def persist():
  t=journal.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8');t.replace(journal)
 def run(script,*args):
  cmd=[sys.executable,'scripts/'+script,'--plan',str(a.plan),'--output',str(a.output),*args];started=time.time();res=subprocess.run(cmd);v['events'].append(dict(script=script,args=args,seconds=time.time()-started,returncode=res.returncode));persist()
  if res.returncode:raise RuntimeError('Stopped after '+script)
 owners=a.owners.split(',')if a.owners else [h['owner']for h in p['hubs']]
 from planning_shared_hubs import city_siting_reviews
 reviews=p.get('city_siting_reviews',city_siting_reviews(p['hubs'],p['cities']))
 pending=[r for r in reviews if set(r['owners'])&set(owners)and not(r.get('status')=='resolved'and r.get('selected_alternative')in r['alternatives']and r.get('evidence'))]
 if pending:ap.error('City siting comparison required before construction: '+str([r['owners']for r in pending]))
 for owner in owners:
  h=next(h for h in p['hubs']if h['owner']==owner);print('COLLECTION '+owner,flush=True)
  mode=p['templates'][h['template']].get('placementMode','joint')if a.mode=='auto'else a.mode
  if mode not in ('road-first','joint','sequential'):ap.error('Unknown template placementMode: '+mode)
  if mode=='road-first':
   if a.defer_walking:ap.error('Road-first placement requires walking acceptance; no deferral')
   flags=['--authorize-build']+(['--isolated-test-save']if a.isolated_test_save else[])+(['--current-map-test']if a.current_map_test else[])
   for stage in ('roads','facilities'):run('road_first_collection.py','build','--stage',stage,'--owner',owner,*flags)
   external=[r['id']for r in p['roads']if r['id'].startswith(owner+'_')and not r.get('templateRoad')]
   if external:run('build_planned_hub_roads.py','build','--owner',owner,'--road-ids',','.join(external))
   v['lastAcceptedCollection']=owner;persist();continue
  if mode=='joint':
   flags=['--authorize-build']+(['--isolated-test-save']if a.isolated_test_save else[])+(['--current-map-test']if a.current_map_test else[])+(['--defer-walking']if a.defer_walking else[])
   run('build_joint_collection.py','build','--owner',owner,*flags)
   external=[r['id']for r in p['roads']if r['id'].startswith(owner+'_')and not r.get('templateRoad')]
   if external:run('build_planned_hub_roads.py','build','--owner',owner,'--road-ids',','.join(external))
   v['lastAcceptedCollection']=owner;persist();continue
  run('fullmap_batch.py','build','--ids',','.join(h['facilities'].values()))
  run('build_planned_hub_roads.py','build','--owner',owner)
  run('audit_planned_hubs.py','--owner',owner)
  v['lastAcceptedCollection']=owner;persist()
 v['collectionsFinished']=time.time();persist()
if __name__=='__main__':main()
