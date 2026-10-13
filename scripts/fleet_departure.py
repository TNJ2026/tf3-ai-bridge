"""Bounded targeted departure observation; finish as soon as all targets pass."""
import argparse,asyncio,json,time
from pathlib import Path
from fullmap_batch import Batch,quote,batch_lock,write_json,StopBatch
from carrier_acceptance import departure_result,policy

SAMPLE='''local wanted=B.json.decode(TARGETS);local CT=api.type.ComponentType
local out={state=B.commands.get_game_state({}),vehicles={},problems={}}
local player=api.engine.util.getPlayer()
for _,line in ipairs(wanted)do
 local owner=api.engine.getComponent(line,CT.PLAYER_OWNED)
 assert(owner and owner.player==player,'Target line is not owned by player')
 assert(api.engine.getComponent(line,CT.LINE),'Target line missing')
 for _,id in ipairs(api.engine.system.transportVehicleSystem.getLineVehicles(line))do
  local v=api.engine.getComponent(id,CT.TRANSPORT_VEHICLE)
  out.vehicles[#out.vehicles+1]={id=id,line=v.line,noPath=v.noPath,userStopped=v.userStopped,
   motion=B.commands.get_vehicle_motion({vehicle=id,resolve_native_path=false})}
 end
end
for _,p in ipairs(api.engine.system.lineSystem.getProblemLines(player))do out.problems[#out.problems+1]=B.toPlain(p)end
return B.json.encode(out)'''


async def observe(batch, lines, seconds=45, interval=2):
    if not lines or any(type(i) is not int or i<0 for i in lines):raise ValueError('Explicit current line IDs required')
    if seconds<=0 or interval<=0:raise ValueError('Positive bounded observation duration required')
    source=SAMPLE.replace('TARGETS',quote(sorted(set(lines))))
    trace={'samples':[],'operationalAccepted':False,'policy':policy()}
    async def sample():return await batch.eval(source)
    def save():write_json(batch.a.output/'fleet_observation.json',trace)
    initial=await batch.session()
    if initial['speedup']!=0:raise StopBatch('Expected paused world')
    before=await sample();trace['before']=before
    expected={v['id']:v['line'] for v in before['vehicles']}
    if set(expected.values())!=set(lines):raise StopBatch('Every target line needs an assigned vehicle')
    result=departure_result(before,expected);trace['departure']=result;save()
    if 'native_fault' in result['vehicles'].values():raise StopBatch('Native line/path fault; diagnose only affected targets')
    if result['accepted']:
        trace.update(operationalAccepted=True,observationCompleted=True);save();return trace
    changed=False
    try:
        current=await batch.call('get_game_state')
        if current['speedup']!=0:raise StopBatch('Speed changed before observation')
        # Mark attempted before dispatch: an unknown reply must not be replayed.
        trace['speedStartAttempted']=True;save()
        await batch.call('set_game_speed',{'speed':1,'expected_speed':0})
        changed=True
        current=await batch.call('get_game_state')
        if current['speedup']!=1:raise StopBatch('Speed readback differs')
        start=time.monotonic();previous=before
        departed={ident for ident,status in result['vehicles'].items() if status=='accepted'}
        while time.monotonic()-start<seconds:
            await asyncio.sleep(min(interval,max(0,seconds-(time.monotonic()-start))))
            snapshot=await sample();trace['samples'].append(snapshot)
            if snapshot['state']['speedup']!=1:raise StopBatch('User changed speed; end observation')
            result=departure_result(snapshot,expected,previous)
            for ident,status in result['vehicles'].items():
                if status=='accepted':departed.add(ident)
                elif status=='departure_pending' and ident in departed:result['vehicles'][ident]='accepted'
            result['accepted']=all(status=='accepted' for status in result['vehicles'].values())
            trace['departure']=result;save()
            if 'native_fault' in result['vehicles'].values():raise StopBatch('Native line/path fault; stop observation')
            if result['accepted']:
                trace.update(operationalAccepted=True,observationCompleted=True);break
            previous=snapshot
        if not trace['operationalAccepted']:trace['status']='departure_pending_at_time_limit'
    finally:
        if changed and batch.b.heartbeat().get('connected'):
            state=await batch.call('get_game_state')
            if state['speedup']==1:
                await batch.call('set_game_speed',{'speed':0,'expected_speed':1})
                trace['restoredPaused']=(await batch.call('get_game_state'))['speedup']==0
                if not trace['restoredPaused']:raise StopBatch('Pause readback differs; no retry')
        save()
    if trace['operationalAccepted']:await batch.save('fleet_observed')
    return trace


async def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--line-ids',required=True,help='Comma-separated current native line IDs')
    ap.add_argument('--seconds',type=int,default=45,help='Upper bound, not a required observation period')
    a=ap.parse_args();a.action='preview';a.ids=None;b=Batch(a)
    with batch_lock(b.b.dir):
        result=await observe(b,[int(x) for x in a.line_ids.split(',')],a.seconds)
    print(json.dumps({'accepted':result['operationalAccepted'],'departure':result['departure']}))


if __name__=='__main__':asyncio.run(main())
