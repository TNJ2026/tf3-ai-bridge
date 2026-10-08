"""Single-proposal HQ access diagnostic; offline prepare or explicit isolated-save test."""
import argparse,asyncio,hashlib,json,math,time,uuid
from pathlib import Path
from types import SimpleNamespace
from batch_warehouses import Bridge,batch_lock,write_json
from fullmap_batch import Batch,quote
from fullmap_workflow import atomic_write

def prepare(plan,snapshot,run_id):
    rows=[f for f in plan['facilities']if f['id']=='HQ']
    if len(rows)!=1:raise ValueError('Exactly one headquarters candidate required')
    hq=rows[0];args={k:hq['args'][k]for k in ('town','x','y','z','rotation')}
    if any(isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v)for v in args.values()):
        raise ValueError('Finite numeric headquarters arguments required')
    if args['town']!=plan['focus_town']or int(args['town'])!=args['town']:raise ValueError('Main town mismatch')
    roads=[o for o in snapshot['obstacles']if o.get('kind')=='BASE_EDGE'and o.get('entity')==hq['road_frontage']['edge_hint']]
    if len(roads)!=1:raise ValueError('Unique surveyed frontage road required')
    road={k:roads[0][k]for k in ('position0','position1','roadTemplate')}
    for key in ('position0','position1'):
        if any(not isinstance(road[key][k],(int,float))or not math.isfinite(road[key][k])for k in ('x','y','z')):
            raise ValueError('Invalid surveyed road coordinates')
    if not isinstance(road['roadTemplate'],str)or not road['roadTemplate']:raise ValueError('Missing road template')
    source=Path(__file__).with_name('hq_access_preview.lua').read_text('utf8')
    return source.replace('INPUT_JSON',quote(dict(args=args,road=road,runId=run_id)))

def analyze(result, *, existing_entities=None):
    """Directed PERSON graph; automatic links attach at actual edge parameters."""
    answer={'entranceConnected':False,'outbound':False,'inbound':False,'constructionReady':False,
            'basis':'Single HQ proposal PERSON network to resolved frontage road; post-build readback required'}
    if not result.get('check',{}).get('clear'):return dict(answer,reason='placement_rejected')
    if existing_entities is None:
        if result.get('nativeProposalCalls')!=1:raise ValueError('Expected exactly one native proposal')
    else:
        if result.get('nativeProposalCalls')!=0:raise ValueError('Existing audit must not generate proposals')
        existing_entities=set(existing_entities)
        if not existing_entities or any(not isinstance(e,int)or e<=0 for e in existing_entities):
            raise ValueError('Positive current HQ network entities required')
        answer['basis']='Readback of existing PERSON lanes and TP_NET_LINK; directed graph, not native simulation acceptance'
    def node(n):return (int(n['entity']),int(n['index']))
    edges={};starts=set();goals=set()
    for net in result['networks']:
        for e in net['edges']:
            k=(net['entity'],e['index'])
            if k in edges:raise ValueError('Duplicate PERSON edge')
            a,b=node(e['from']),node(e['to'])
            if not isinstance(e['forwardOnly'],bool):raise ValueError('Missing direction')
            edges[k]={'a':a,'b':b,'oneway':e['forwardOnly'],'points':[(0.,a),(1.,b)]}
            # Only one new construction, no new roads, enters this proposal.
            if (net['entity']<0 if existing_entities is None else net['entity'] in existing_entities):starts.update((a,b))
            if net['entity']==result['road']:goals.update((a,b))
    graph={}
    def add(a,b):graph.setdefault(a,set()).add(b)
    def attach(p):
        k=(p['entity'],p['index']);e=edges.get(k);t=p['param']
        if not isinstance(t,(int,float))or not math.isfinite(t)or not 0<=t<=1:raise ValueError('Invalid link parameter')
        if e is None:return None
        n=e['a']if t==0 else e['b']if t==1 else('link',*k,t)
        e['points'].append((t,n));return n
    for link in result['links']:
        a,b=attach(link['from']),attach(link['to'])
        if a is not None and b is not None:add(a,b);add(b,a)
    for e in edges.values():
        points=sorted(e['points'],key=lambda p:p[0])
        for (_,a),(_,b)in zip(points,points[1:]):
            add(a,b)
            if not e['oneway']:add(b,a)
    def reachable(a,b):
        pending=list(a);seen=set(a)
        while pending:
            n=pending.pop()
            if n in b:return True
            for nxt in graph.get(n,()):
                if nxt not in seen:seen.add(nxt);pending.append(nxt)
        return False
    # Test every HQ lane endpoint. Existential start sets can falsely pass both
    # directions through different ends of a one-way entrance lane.
    answer.update(hqNodes=len(starts),roadNodes=len(goals),
                  outbound=bool(starts)and all(reachable({n},goals)for n in starts),
                  inbound=bool(starts)and all(reachable(goals,{n})for n in starts))
    answer['entranceConnected']=bool(starts and goals and answer['outbound']and answer['inbound'])
    return answer

async def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    mode=ap.add_mutually_exclusive_group();mode.add_argument('--prepare-only',action='store_true');mode.add_argument('--isolated-test-save',action='store_true')
    mode.add_argument('--current-map-test',action='store_true',help='Only with explicit user authorization to test the currently displayed city')
    a=ap.parse_args()
    if not(a.prepare_only or a.isolated_test_save or a.current_map_test):
        raise RuntimeError('Disabled after native access violation: use --prepare-only offline; repaired native diagnostic requires an explicitly confirmed --isolated-test-save')
    p=json.loads(a.plan.read_text('utf8'));snapshot=a.plan.parent/'snapshot.json'
    if not snapshot.exists():snapshot=Path(p['snapshot'])
    run_id=uuid.uuid4().hex;code=prepare(p,json.loads(snapshot.read_text('utf8')),run_id)
    folder=a.output.with_suffix('.attempt');receipt=folder/'receipt.json'
    if a.output.exists()or receipt.exists():raise RuntimeError('Existing result/attempt; inspect it, never automatically replay')
    folder.mkdir(parents=True,exist_ok=True);atomic_write(folder/'preview.lua',code)
    if a.prepare_only:
        write_json(a.output,{'prepared':True,'gameCalls':0,'nativeValidated':False,'source':str(folder/'preview.lua')});return
    args=SimpleNamespace(plan=a.plan,output=folder,action='preview',ids=None,limit=0)
    b=Batch(args)
    with batch_lock(b.b.dir):
        state=await b.session()
        if state['speedup']!=0:raise RuntimeError('Diagnostic test must already be paused; no automatic speed change')
        camera=None
        if a.current_map_test:
            camera=await b.call('eval',{'code':'local p=api.gui.camera.getCenter();return {x=p.x,y=p.y,z=p.z}'},False)
            current=min(p['cities'],key=lambda c:math.hypot(c['position']['x']-camera['x'],c['position']['y']-camera['y']))
            if current['id']!=p['focus_town']:raise RuntimeError('Displayed city differs from the HQ plan; resurvey before testing')
        await b.save('hq_access_diagnostic_before')
        event={'attempted':True,'runId':run_id,'state':state,'at':time.time(),'sourceSha256':hashlib.sha256(code.encode()).hexdigest(),
               'bridgeSha256':hashlib.sha256(b.source.encode()).hexdigest(),'outcome':'pending','isolatedSaveDeclared':a.isolated_test_save,
               'currentMapTestAuthorized':a.current_map_test,'camera':camera,'commitEnabled':False}
        write_json(receipt,event)
        try:
            result=await b.eval(code);write_json(folder/'native_result.json',result)
            result['access']=analyze(result);write_json(a.output,result)
            event.update(outcome='returned',access=result['access']);print(json.dumps(result['access']))
        except BaseException as exc:
            event.update(outcome='error_or_unknown',error=str(exc));raise
        finally:event['finishedAt']=time.time();write_json(receipt,event);b.flush()

if __name__=='__main__':asyncio.run(main())
