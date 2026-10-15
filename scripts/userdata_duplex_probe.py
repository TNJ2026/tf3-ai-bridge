"""Explicit external-first, data-only 100-round native userdata mailbox test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

from userdata_roundtrip_probe import atomic, save
from validate_bridge_compile import check_bridge_compile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server/src'))
from tf3_mcp.bridge import encode_message, decode_message

TAG='[TNJ_USERDATA_DUPLEX_V1]'


def prepare(mod,userdata,out):
    out.mkdir(parents=True,exist_ok=False)
    script=mod/'bridge.script.lua';before=script.read_bytes();source=before.decode('utf-8')
    uid=uuid.uuid4().hex
    config=dict(id=uid,request='tnj_mcp_duplex_'+uid+'_req.preset',
                response='tnj_mcp_duplex_'+uid+'_resp.preset',rounds=100)
    paths={k:str((userdata/'mod_presets'/(config[k]+'.lua')).resolve()) for k in ('request','response')}
    assert all(not Path(p).exists() for p in paths.values())
    factory=Path(__file__).with_suffix('.lua').read_text(encoding='utf-8')
    lua_config='{'+','.join(k+'='+json.dumps(v) for k,v in config.items())+',session=terrainEpoch}'
    hook=('local userdataDuplexTick=(function()\n'+factory+'\nend)()('+lua_config+
        ',function(row) log("'+TAG+'",json.encode(row)) end,wallClock,'
        'function(value) assert(type(value)=="table" and type(value.hex)=="string","Invalid envelope");'
        'return json.decode(hexDecode(value.hex)) end,'
        'function(value) return {hex=hexEncode(json.encode(value))} end)\n\n')
    assert source.count('local bridgeScript = {')==1
    source=source.replace('local bridgeScript = {',hook+'local bridgeScript = {',1)
    needle='\tguiUpdate = function(_userParams, state, _guiState)\n'
    assert source.count(needle)==1
    source=source.replace(needle,needle+'\t\tif userdataDuplexTick then userdataDuplexTick(); return end\n',1)
    compiled=check_bridge_compile(source)
    data=source.encode('utf-8');(out/'bridge.before.lua').write_bytes(before)
    record=dict(config=config,paths=paths,script=str(script.resolve()),
                log=str((userdata/'crash_dump/stdout.txt').resolve()),
                installedSha256=hashlib.sha256(data).hexdigest(),compile=compiled,status='prepared_requires_reload')
    save(out/'probe.json',record);atomic(script,data)
    return record


def events(record):
    path=Path(record['log'])
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-512*1024))
        lines=stream.read().decode('utf-8',errors='replace').splitlines()
    result=[]
    for line in lines:
        if TAG not in line or record['config']['id'] not in line:continue
        try: row=json.loads(line.split(TAG,1)[1])
        except ValueError:continue
        if row.get('probeId')==record['config']['id']:result.append(row)
    return result


def watch(out):
    record=json.loads((out/'probe.json').read_text(encoding='utf-8'));config=record['config']
    req=Path(record['paths']['request']);resp=Path(record['paths']['response'])
    result=dict(status='waiting_for_reload',exchanges=[],worldModified=False)
    save(out/'result.json',result)
    try:
        deadline=time.monotonic()+600
        session=None
        while time.monotonic()<deadline:
            for row in events(record):
                if row['event']=='failed':raise RuntimeError(str(row))
                if row['event']=='ready':session=row['session']
            if session:break
            time.sleep(0.5)
        if not session:raise TimeoutError('Waiting for diagnostic reload timed out')
        assert not req.exists() and not resp.exists(), 'Mailbox must start absent'
        result.update(status='running',session=session,externalCreatedFirst=True)
        print('Native ready; starting external-first mailbox exchanges',flush=True)
        def exchange(seq,payload,expected='ok',session_override=None,processed=None):
            packet=dict(probeId=config['id'],session=session_override or session,seq=seq,
                        attempt=uuid.uuid4().hex,op='echo',payload=payload)
            start=time.monotonic();atomic(req,encode_message(packet).encode('utf-8'))
            while time.monotonic()-start<8:
                answer=None
                try:answer=decode_message(resp.read_text(encoding='utf-8'))
                except (OSError,UnicodeError):pass
                if isinstance(answer,dict) and answer.get('attempt')==packet['attempt']:
                    assert answer.get('probeId')==config['id'] and answer.get('session')==session
                    assert answer.get('seq')==seq and answer.get('status')==expected, answer
                    assert answer.get('processed')==(seq if processed is None else processed),answer
                    if expected!='rejected':assert answer.get('payload')==payload
                    result['exchanges'].append(dict(seq=seq,status=expected,processed=answer['processed'],
                        payloadBytes=len(payload.encode('utf-8')),latencySeconds=time.monotonic()-start,
                        requestId=packet['attempt'],reason=answer.get('reason')))
                    save(out/'result.json',result)
                    return
                time.sleep(0.025)
            raise TimeoutError('No matching reply; request is not resent')
        for seq in range(1,config['rounds']+1):
            size=(64,1024,8192)[(seq-1)%3]
            payload=('中文往返🙂\\\"\n:'+str(seq)+':')+('x'*size)
            exchange(seq,payload)
            if seq==5:
                exchange(seq,payload,'duplicate',processed=seq)
                exchange(seq,'changed','rejected',processed=seq)
                exchange(seq+1,'stale','rejected',session_override='wrong_session',processed=seq)
                exchange(seq+2,'gap','rejected',processed=seq)
            if seq==50:
                baseline=resp.read_bytes();time.sleep(10)
                assert resp.read_bytes()==baseline,'Idle request was processed again'
                result['idleTenSecondsUnchanged']=True
            if seq%25==0:print('Verified',seq,'unique requests',flush=True)
        finish=dict(probeId=config['id'],session=session,seq=config['rounds']+1,
                    attempt=uuid.uuid4().hex,op='finish')
        atomic(req,encode_message(finish).encode('utf-8'))
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            rows=events(record)
            complete=[r for r in rows if r['event']=='complete']
            if complete:
                assert complete[-1]['processed']==100 and complete[-1]['cleaned']
                assert not req.exists() and not resp.exists()
                result.update(status='passed',nativeResult=complete[-1],events=rows)
                return result
            time.sleep(0.1)
        raise TimeoutError('Native cleanup acknowledgement missing')
    except BaseException as exc:
        result.update(status='failed',error=str(exc));raise
    finally:
        for path in (req,resp):
            if path.exists():
                value=decode_message(path.read_text(encoding='utf-8'))
                if isinstance(value,dict) and value.get('probeId')==config['id']:
                    (out/('cleanup_'+path.name)).write_bytes(path.read_bytes());path.unlink()
                    result['hostCleanup']=True
                else:result['cleanupBlocked']=str(path)
        script=Path(record['script'])
        if hashlib.sha256(script.read_bytes()).hexdigest()==record['installedSha256']:
            atomic(script,(out/'bridge.before.lua').read_bytes());result['installedScriptRestored']=True
        else:result['installedScriptRestored']=False
        result['testFilesAbsent']=not req.exists() and not resp.exists()
        save(out/'result.json',result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','watch'))
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--mod',type=Path);p.add_argument('--userdata',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if a.mod is None or a.userdata is None:p.error('prepare requires --mod and --userdata')
        r=prepare(a.mod,a.userdata,a.evidence)
    else:r=watch(a.evidence)
    print(json.dumps({k:v for k,v in r.items() if k not in ('events','exchanges','compile')},ensure_ascii=False),flush=True)
