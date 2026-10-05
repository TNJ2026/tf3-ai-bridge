"""Experimental fish-port collection: offline prepare, guarded preview/build, static readback."""
import argparse,asyncio,hashlib,json,math,time
from pathlib import Path
from fullmap_batch import Batch,StopBatch,batch_lock,quote,write_json
from fullmap_workflow import atomic_write
from hub_joint_prototype import compile_spec,probe
from commit_joint_test import GUARD
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'config/planning_templates/fish_port_air.json'

def prepare(template):
    spec=compile_spec(json.loads(template.read_text('utf8')))
    if spec['collectionKind']!='fish_port':raise ValueError('Fish-port template required')
    for f in spec['facilities']:
        if not all(isinstance(f['localPosition'].get(k),(int,float))and math.isfinite(f['localPosition'][k])for k in ('x','y','z')):raise ValueError('Invalid facility position')
        if not math.isfinite(f['relativeRotation']):raise ValueError('Invalid rotation')
    return spec

def attempt(spec,origin):
    code=probe(spec).replace('local isolatedTestConfirmed=false','local isolatedTestConfirmed=true').replace(
        'local origin=nil -- {x=...,y=...,rotation=...}; choose empty land in the test save','local origin=B.json.decode('+quote(origin)+')')
    # Share the exact pre-submit path checks, without inventory or world commands.
    checks=GUARD.split('local CT=api.type.ComponentType')[0]
    assert 'sendCommand' not in checks
    path_check="""local previewPaths=nil
if not pd.errorState.critical and #pd.errorState.infos==0 and #pd.errorState.messages==0 and #pd.errorState.warnings==0 and #collisions==0 then
"""+checks+'\npreviewPaths=paths\nend\n'
    return code.replace('return B.json.encode({previewOnly=true',path_check+'return B.json.encode({previewOnly=true').replace(
        'connectionsVerified=false,','connectionsVerified=previewPaths~=nil,previewPaths=previewPaths,')

def clear(result):
    e=result.get('errorState',{})
    return e.get('critical') is False and all(e.get(k)==[] for k in ('messages','infos','warnings')) and result.get('collisions')==[]

async def execute(a):
    a.output.mkdir(parents=True,exist_ok=True)
    if a.action=='prepare':
        spec=prepare(a.template);write_json(a.output/'joint_spec.json',spec)
        atomic_write(a.output/'isolated_preview.lua',probe(spec))
        print(json.dumps({'prepared':True,'facilities':len(spec['facilities']),'gameCalls':0,'nativeVerified':False}));return
    if not a.plan:raise ValueError('--plan is required for current map identity checks')
    if a.action in ('preview','build') and not a.isolated_test_save:raise ValueError('Experimental native proposal requires --isolated-test-save after confirming the actual save')
    if a.action=='build' and not a.authorize_build:raise ValueError('Explicit future build authorization required')
    a.ids=None;a.limit=0;b=Batch(a)
    receipt_path=a.output/'fish_port_receipt.json';commit_path=a.output/'fish_port_commit.json'
    def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()
    with batch_lock(b.b.dir):
        state=await b.session()
        if a.action in ('preview','build') and state['speedup']!=0:raise StopBatch('Pause the test save before native testing')
        if a.action=='preview':
            if receipt_path.exists():raise StopBatch('Preview already attempted; inspect evidence, use a new directory for revised design')
            if a.x is None or a.y is None:raise ValueError('Explicit --x and --y required; never infer a camera position')
            origin={'x':a.x,'y':a.y,'rotation':a.rotation}
            if not all(math.isfinite(v) for v in origin.values()):raise ValueError('Finite placement required')
            spec=prepare(a.template);code=attempt(spec,origin)
            write_json(a.output/'joint_spec.json',spec);atomic_write(a.output/'attempt.lua',code)
            await b.save('fish_port_before')
            receipt={'specDigest':digest(spec),'origin':origin,'state':state,'attempted':True,'outcome':'pending','codeDigest':hashlib.sha256(code.encode()).hexdigest()}
            write_json(receipt_path,receipt)
            try:
                result=await b.eval(code);write_json(a.output/'preview.json',result)
                accepted=clear(result) and result.get('connectionsVerified') is True
                receipt.update(outcome='returned',previewPassed=accepted);write_json(receipt_path,receipt)
                if not accepted:raise StopBatch('Joint native preview or vehicle paths rejected; no build')
            except BaseException:
                if receipt['outcome']=='pending':receipt['outcome']='unknown';write_json(receipt_path,receipt)
                raise
            print('Joint preview passed; no construction submitted');return
        receipt=json.loads(receipt_path.read_text('utf8'));spec=json.loads((a.output/'joint_spec.json').read_text('utf8'))
        if digest(spec)!=receipt['specDigest']:raise StopBatch('Prepared spec changed')
        if a.action=='build':
            if commit_path.exists():raise StopBatch('Submission already attempted; verify, never replay')
            if not receipt.get('previewPassed'):raise StopBatch('No accepted recorded preview')
            old=receipt['state']
            if any(state[k]!=old[k]for k in ('player','world','gameTime'))or state['tickCount']<old['tickCount']:raise StopBatch('Session changed since preview')
            code=attempt(spec,receipt['origin'])
            if hashlib.sha256(code.encode()).hexdigest()!=receipt['codeDigest']:raise StopBatch('Proposal implementation changed')
            await b.save('fish_port_commit_before')
            event={'attempted':True,'outcome':'pending','at':time.time()};write_json(commit_path,event)
            # Rebuilds/validates the same proposal and binds generated ports in this invocation.
            try:
                result=await b.eval(code.split('return B.json.encode({previewOnly=true')[0]+GUARD)
                write_json(a.output/'commit_result.json',result)
                if not result.get('callback',{}).get('received') or result['callback'].get('success')is not True:raise StopBatch('Commit outcome incomplete; reconcile')
                event['outcome']='returned';write_json(commit_path,event)
            except BaseException:
                event['outcome']='unknown_or_failed';write_json(commit_path,event);raise
        built=json.loads((a.output/'commit_result.json').read_text('utf8'))
        lua=(ROOT/'scripts/fish_port_audit.lua').read_text('utf8')
        audit=await b.eval(lua.replace('SPEC_JSON',quote(spec)).replace('ORIGIN_JSON',quote(receipt['origin'])).replace('ADDED_JSON',quote(built['added'])))
        write_json(a.output/'fish_port_acceptance.json',audit)
        if not audit.get('staticAccepted'):raise StopBatch('Static acceptance incomplete; no resubmission')
        if a.action=='build':await b.save('fish_port_checkpoint')
        print(json.dumps({'staticAccepted':True,'operationalAccepted':False}))
    b.flush()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','preview','build','verify'],default='prepare',nargs='?')
    ap.add_argument('--template',type=Path,default=DEFAULT);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--plan',type=Path)
    ap.add_argument('--x',type=float);ap.add_argument('--y',type=float);ap.add_argument('--rotation',type=float,default=0)
    ap.add_argument('--isolated-test-save',action='store_true');ap.add_argument('--authorize-build',action='store_true')
    asyncio.run(execute(ap.parse_args()))
if __name__=='__main__':main()
