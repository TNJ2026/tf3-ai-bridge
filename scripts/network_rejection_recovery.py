"""Prepare an opt-in immutable migration from an audited native rejection receipt.

No game calls. Not a general pending reset: only the exact pre-dispatch network
signature error is eligible, with a matching consumed preview lineage and map.
"""
import hashlib
import json
import math
import re


# Reviewed installed image: its BASE_EDGE enumeration at line5254 precedes applyProposal.
LEGACY_ENUMERATION_IMAGES = {'1ee0c71d2ea2d83e55c8b5f7f3e4004449199df14eafe3b4d559bdb333ea938e': 5254}


def prepare_recovery(receipt_path, survey_path, source_path=None, *, allow_industry_additions=False):
    raw=receipt_path.read_bytes()
    r=json.loads(raw.decode('utf-8'))
    response=r.get('response',{})
    rid=r.get('id','')
    assert re.fullmatch(r'[0-9a-f]{32}',rid), 'Invalid request ID'
    assert r.get('command')=='commit_network' and r.get('kind')=='build' and r.get('status')=='received'
    assert response.get('id')==rid and response.get('cmd')=='commit_network' and response.get('ok') is False
    error=response.get('error','')
    signature_error=re.fullmatch(r'\[string "[^"\r\n]*bridge\.script\.lua"\]:[0-9]+: Network endpoints or template changed',error)
    rejection_kind='network_signature_before_dispatch'
    source_hash=None
    if not signature_error:
        assert source_path is not None, 'Unknown rejection requires the reviewed original source image'
        image=source_path.read_bytes();source_hash=hashlib.sha256(image).hexdigest()
        line=LEGACY_ENUMERATION_IMAGES.get(source_hash)
        assert line is not None, 'Source image was not reviewed for pre-dispatch enumeration failure'
        match=re.match(r'\[string "[^"\r\n]*bridge\.script\.lua"\]:([0-9]+): Cannot loop over this component type\nstack traceback:\n    =\[C\]\(-1\): forEachEntityWithComponent\n',error)
        assert match and int(match[1])==line, 'Not the reviewed pre-dispatch enumeration error'
        text=image.decode('utf-8')
        assert 'local HEADLESS_GENERATION = "'+r['generation']+'"' in text
        assert 'componentTypes().BASE_EDGE)' in text.splitlines()[line-1]
        rejection_kind='network_edge_enumeration_before_dispatch'

    prefix=rid+' commit_network '
    assert r.get('input','').startswith(prefix)
    args=json.loads(r['input'][len(prefix):])
    assert set(args)=={'preview_token'}
    token=args['preview_token'];session=r['session']
    assert token.startswith('ui-network:'+session+':') and token.rsplit(':',1)[1].isdigit()
    assert re.fullmatch('[0-9a-f]{32}',r.get('generation',''))
    sample=json.loads(survey_path.read_text(encoding='utf-8'))
    assert sample.get('status')=='completed'
    rows={v['command']:v['response'] for v in sample['requests']}
    assert rows['get_map_info']['ok'] and rows['get_game_state']['ok']
    m=rows['get_map_info']['result'];game=rows['get_game_state']['result']
    identity={'width':m['width'],'height':m['height'],'towns':{},'industries':{}}
    for kind,label in [('towns','name'),('industries','fileName')]:
        assert m[kind], 'Empty map identity'
        for v in m[kind]:
            assert type(v['id']) is int and str(v['id']) not in identity[kind]
            assert isinstance(v[label],str) and v[label]
            pos=v['position'];assert set(pos)=={'x','y'}
            assert all(type(n) in (int,float) and math.isfinite(n) for n in pos.values())
            identity[kind][str(v['id'])]={label:v[label],'position':pos}
    return dict(id=rid,cmd='commit_network',ok=False,error=error,session=session,
                token=token,player=game['player'],map=identity,
                receiptSha256=hashlib.sha256(raw).hexdigest(),rejectionKind=rejection_kind,sourceSha256=source_hash,
                identityPolicy='original_objects_plus_industry_additions' if allow_industry_additions else 'exact')


def lua_literal(value):
    encoded=json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('utf-8')
    return '"'+''.join('\\%03d'%b for b in encoded)+'"'
