import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from tf3_mcp import no_gui_recovery as recovery
from tf3_mcp.bridge import encode_message


def evidence(tmp_path, monkeypatch):
    source=tmp_path/'bridge.lua';source.write_bytes(b'audited fixture')
    monkeypatch.setattr(recovery,'WORLD_MODULE_SOURCE_SHA256',hashlib.sha256(source.read_bytes()).hexdigest())
    row=dict(id='a'*32,kind='build',command='list_world_actions',input='a'*32+' list_world_actions',
             transport='userdata',status='published',session='s',generation='g',slot=5,expires=20)
    env={k:row[k] for k in ('session','generation','slot','expires','kind','input')}
    row['publicationSha256']=hashlib.sha256(encode_message(env).encode()).hexdigest()
    reason="module 'tnj_tf3_ai_bridge::/tf3_mcp_bridge/world_actions' not found:"
    events=[dict(session='s',generation='g',slot=5,status=status) for status in ['consumed','dispatched','stopped']]
    events[0]['id']=row['id'];events[1].update(id=row['id'],detail='init.lua:100: '+reason)
    events[2]['error']='bridge.script.lua:10012: Dispatch failed or unknown: init.lua:100: '+reason
    def write(events):
        log=tmp_path/'stdout.txt'
        log.write_text(''.join(recovery.TAG+' '+json.dumps(e)+'\n' for e in events),encoding='utf-8')
        row.update(inode=log.stat().st_ino,offset=0,anchor='')
        return SimpleNamespace(log=log)
    return row,events,source,write


def test_exact_module_rejection_preserves_failure(tmp_path,monkeypatch):
    row,events,source,write=evidence(tmp_path,monkeypatch)
    result=recovery.world_module_load_rejection(write(events),row,source)
    assert result['engineDispatchAttempted'] is False
    assert result['retryAllowed'] is False
    assert result['nativeEvents']==events


@pytest.mark.parametrize('case',['source','digest','command','arguments','id','reason','missing_stop','extra_event','anchor'])
def test_recovery_refuses_changed_evidence(tmp_path,monkeypatch,case):
    row,events,source,write=evidence(tmp_path,monkeypatch)
    if case=='id':events[1]['id']='b'*32
    if case=='reason':events[1]['detail']='another failure'
    if case=='missing_stop':events.pop()
    if case=='extra_event':events.append(copy.deepcopy(events[-1]))
    host=write(events)
    if case=='source':source.write_bytes(b'changed')
    if case=='digest':row['publicationSha256']='bad'
    if case=='command':row['command']='commit_world_action'
    if case=='arguments':row['input']+=' {}'
    if case=='anchor':row['anchor']='aa';row['offset']=1
    with pytest.raises(ValueError):recovery.world_module_load_rejection(host,row,source)
