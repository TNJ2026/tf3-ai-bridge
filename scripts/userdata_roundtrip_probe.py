"""Prepare/watch an explicit single-file native userdata A -> external B probe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from validate_bridge_compile import check_bridge_compile

TAG = '[TNJ_USERDATA_PROBE_V1]'


def atomic(path, data):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_bytes(data)
    os.replace(temp, path)


def save(path, value):
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))


def prepare(mod, userdata, evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    script = mod / 'bridge.script.lua'
    before = script.read_bytes()
    source = before.decode('utf-8')
    probe_id = uuid.uuid4().hex
    config = dict(id=probe_id, filename='tnj_mcp_probe_'+probe_id+'.preset',
                  a='probe_a_'+probe_id, b='probe_b_'+probe_id)
    path = userdata / 'mod_presets' / (config['filename']+'.lua')
    if path.exists():
        raise ValueError('Random test file already exists')
    factory = Path(__file__).with_suffix('.lua').read_text(encoding='utf-8')
    lua_config = '{' + ','.join(k+'='+json.dumps(v) for k,v in config.items()) + '}'
    injection = ('local userdataProbeTick = (function()\n'+factory+'\nend)()('+lua_config+
        ', function(row) log("'+TAG+'",json.encode(row)) end, wallClock)\n\n')
    assert source.count('local bridgeScript = {') == 1
    source = source.replace('local bridgeScript = {', injection+'local bridgeScript = {',1)
    hook = '\tguiUpdate = function(_userParams, state, _guiState)\n'
    assert source.count(hook) == 1
    source = source.replace(hook, hook+'\t\tif userdataProbeTick then userdataProbeTick(); return end\n',1)
    compiled = check_bridge_compile(source)
    (evidence/'bridge.before.lua').write_bytes(before)
    installed = source.encode('utf-8')
    record = dict(config=config, testFile=str(path.resolve()), script=str(script.resolve()),
        log=str((userdata/'crash_dump/stdout.txt').resolve()),
        installedSha256=hashlib.sha256(installed).hexdigest(),
        status='prepared_requires_reload', compile=compiled, worldModified=False)
    save(evidence/'probe.json',record)
    atomic(script,installed)
    return record


def watch(evidence, timeout=600):
    record = json.loads((evidence/'probe.json').read_text(encoding='utf-8'))
    config=record['config'];path=Path(record['testFile']);log=Path(record['log'])
    seen=set();events=[];wrote_b=False
    result=dict(status='waiting_for_reload',events=events,worldModified=False)
    save(evidence/'result.json',result)
    deadline=time.monotonic()+timeout
    try:
        while time.monotonic()<deadline:
            with log.open('rb') as stream:
                stream.seek(max(0,log.stat().st_size-512*1024))
                lines=stream.read().decode('utf-8',errors='replace').splitlines()
            for line in lines:
                if TAG not in line or config['id'] not in line:continue
                try: row=json.loads(line.split(TAG,1)[1])
                except ValueError:continue
                if row.get('probeId')!=config['id']:continue
                key=json.dumps(row,sort_keys=True)
                if key in seen:continue
                seen.add(key);events.append(row)
                print(json.dumps(row,ensure_ascii=False),flush=True)
                if row['event']=='read_a' and not wrote_b:
                    data=path.read_bytes()
                    if config['id'].encode() not in data or data.count(config['a'].encode())!=1:
                        raise ValueError('Native A file ownership/marker mismatch')
                    (evidence/'native_a.lua').write_bytes(data)
                    replacement=data.replace(config['a'].encode(),config['b'].encode(),1)
                    (evidence/'external_b.lua').write_bytes(replacement)
                    atomic(path,replacement);wrote_b=True
                    result['externalBWritten']=True
                if row['event'] in ('complete','failed'):
                    result['status']='passed' if (row['event']=='complete' and row.get('cleaned')
                        and wrote_b and not path.exists()) else 'failed'
                    result['nativeResult']=row
                    return result
            save(evidence/'result.json',result)
            time.sleep(0.5)
        result['status']='timeout'
        return result
    except BaseException as exc:
        result['status']='error';result['error']=str(exc)
        raise
    finally:
        # No commands or broad directory cleanup. Only this run's exact owned file.
        if path.exists():
            data=path.read_bytes()
            if config['id'].encode() in data and (config['a'].encode() in data or config['b'].encode() in data):
                (evidence/'file_before_cleanup.lua').write_bytes(data)
                path.unlink();result['hostCleanup']=True
            else:result['cleanupBlocked']='Test file ownership changed'
        script=Path(record['script'])
        if hashlib.sha256(script.read_bytes()).hexdigest()==record['installedSha256']:
            atomic(script,(evidence/'bridge.before.lua').read_bytes())
            result['installedScriptRestored']=True
        else:result['installedScriptRestored']=False
        result['testFileAbsent']=not path.exists()
        save(evidence/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','watch'))
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--mod',type=Path)
    parser.add_argument('--userdata',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':
        if args.mod is None or args.userdata is None:parser.error('prepare needs --mod and --userdata')
        r=prepare(args.mod,args.userdata,args.evidence)
    else:r=watch(args.evidence)
    print(json.dumps(r,ensure_ascii=False),flush=True)
