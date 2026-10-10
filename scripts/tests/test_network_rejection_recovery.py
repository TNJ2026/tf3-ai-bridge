import json
import pytest
from network_rejection_recovery import prepare_recovery, lua_literal
from validate_bridge_compile import check_bridge_compile


@pytest.mark.parametrize('change',[None,'success','native_error','other_command','wrong_response_id','wrong_token_session','duplicate_town','bad_survey','partial_error'])
def test_recovery_installer_only_accepts_original_exact_rejection(tmp_path,change):
    rid='a'*32;session='old-session'
    r={'id':rid,'command':'commit_network','kind':'build','status':'received','session':session,
       'generation':'b'*32,'input':rid+' commit_network '+json.dumps({'preview_token':'ui-network:'+session+':1'}),
       'response':{'id':rid,'cmd':'commit_network','ok':False,'error':'[string "C:/mod/bridge.script.lua"]:123: Network endpoints or template changed'}}
    m={'width':1000,'height':1000,'towns':[{'id':1,'name':'Town','position':{'x':1,'y':2}}],
       'industries':[{'id':2,'fileName':'farm','position':{'x':3,'y':4}}]}
    sample={'status':'completed','requests':[{'command':'get_map_info','response':{'ok':True,'result':m}},
                                           {'command':'get_game_state','response':{'ok':True,'result':{'player':3}}}]}
    if change=='success':r['response']['ok']=True
    elif change=='native_error':r['response']['error']='native unknown outcome'
    elif change=='other_command':r['command']='commit_facility'
    elif change=='wrong_response_id':r['response']['id']='c'*32
    elif change=='wrong_token_session':r['session']='other'
    elif change=='duplicate_town':m['towns'].append(m['towns'][0])
    elif change=='bad_survey':sample['status']='stopped_incomplete'
    elif change=='partial_error':r['response']['error']='possibly built: '+r['response']['error']
    a=tmp_path/'receipt.json';b=tmp_path/'survey.json'
    a.write_text(json.dumps(r),encoding='utf-8');b.write_text(json.dumps(sample),encoding='utf-8')
    if change:
        with pytest.raises(AssertionError):prepare_recovery(a,b)
    else:
        v=prepare_recovery(a,b);assert v['id']==rid and v['map']['towns']['1']['name']=='Town'
        assert v['identityPolicy']=='exact'
        assert prepare_recovery(a,b,allow_industry_additions=True)['identityPolicy']=='original_objects_plus_industry_additions'
        assert check_bridge_compile('local recovery='+lua_literal(v)+'; return recovery')['executed'] is False


@pytest.mark.parametrize('mode',['ok','unreviewed','wrong_line','wrong_generation','missing_source'])
def test_legacy_enumeration_requires_exact_reviewed_source_image(tmp_path,monkeypatch,mode):
    import hashlib
    import network_rejection_recovery as module
    generation='b'*32;rid='a'*32
    source=('local HEADLESS_GENERATION = "'+generation+'"\n'+
            'local existing={};api.engine.forEachEntityWithComponent(function(id)existing[id]=true end,componentTypes().BASE_EDGE)\n')
    image=tmp_path/'before.lua';image.write_text(source,encoding='utf-8')
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    monkeypatch.setattr(module,'LEGACY_ENUMERATION_IMAGES',{digest:2})
    error='[string "C:/bridge.script.lua"]:2: Cannot loop over this component type\nstack traceback:\n    =[C](-1): forEachEntityWithComponent\n'
    r={'id':rid,'command':'commit_network','kind':'build','status':'received','session':'s','generation':generation,
       'input':rid+' commit_network '+json.dumps({'preview_token':'ui-network:s:1'}),
       'response':{'id':rid,'cmd':'commit_network','ok':False,'error':error}}
    sample={'status':'completed','requests':[
      {'command':'get_map_info','response':{'ok':True,'result':{'width':1,'height':1,'towns':[{'id':1,'name':'Town','position':{'x':0,'y':0}}], 'industries':[{'id':2,'fileName':'farm','position':{'x':1,'y':1}}]}}},
      {'command':'get_game_state','response':{'ok':True,'result':{'player':3}}}]}
    if mode=='unreviewed':image.write_text(source+'-- changed',encoding='utf-8')
    elif mode=='wrong_line':r['response']['error']=error.replace(']:2:',']:3:')
    elif mode=='wrong_generation':r['generation']='c'*32
    a=tmp_path/'receipt.json';b=tmp_path/'survey.json'
    a.write_text(json.dumps(r),encoding='utf-8');b.write_text(json.dumps(sample),encoding='utf-8')
    if mode=='ok':assert prepare_recovery(a,b,image)['rejectionKind']=='network_edge_enumeration_before_dispatch'
    else:
        with pytest.raises(AssertionError):prepare_recovery(a,b,None if mode=='missing_source' else image)
