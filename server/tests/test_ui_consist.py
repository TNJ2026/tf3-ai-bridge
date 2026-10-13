"""Bounded consist preview/commit through real bridge handlers; native API mocked."""
import json
import pytest
from test_e2e import FakeGame, SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments

@pytest.mark.parametrize('mode',['sync','deferred','lost','reject','expired','changed','foreign','nonrail','stale_epoch','unknown_model','mu','bad_quote','partial','resource_changed','owner_changed','road_depot','disabled_rail','electric_depot','depot_changed'])
def test_consist_single_purchase_and_replay(tmp_path,mode):
    g=FakeGame(tmp_path/'game');lua=g.lua;lua.globals().mode=mode
    lua.execute("""
      now=1;os.clock=function()return now end;calls=0;price=200000
      components[300]={[10]={player=2}}
      -- Use actual component enum rather than relying on fixture index for depot.
      api.type.enum.TransportMode.ELECTRIC_TRAIN=8
      components[300][api.type.ComponentType.VEHICLE_DEPOT]={transportModes={[7]=true,[8]=false}}
      api.engine.util.vehicle=api.engine.util.vehicle or {}
      api.engine.util.vehicle.getPartPrice=function(part)return part.part.modelId==52 and price or 50000 end
      local get,find,name,each=api.res.modelRep.get,api.res.modelRep.find,api.res.modelRep.getName,api.res.modelRep.forEachModelWithMetadata
      local wagon={metadata={transportVehicle={carrier=api.type.enum.Carrier.RAIL,compartments={{loadConfigs={{cargoEntry={capacity=16}}}}}}}}
      api.res.modelRep.get=function(id)if id==53 then return wagon end;return get(id)end
      api.res.modelRep.find=function(n)if n=="wagon.mdl" then return 53 end;return find(n)end
      api.res.modelRep.getName=function(id)if id==53 then return "wagon.mdl" end;return name(id)end
      api.res.modelRep.forEachModelWithMetadata=function(k,f)each(k,f);f("wagon.mdl")end
      local old=api.cmd.sendCommand
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {event=true,id=id,name=name,param=param}end
      api.cmd.sendCommand=function(cmd,cb)
       if cmd.event then forwarded=cmd;return end
       calls=calls+1;last_config=cmd.config
       finish=function()
        if mode=='reject' then cb({},false,{}) elseif mode=='partial' then cb({},true,{}) else old(cmd,cb) end
       end
       if mode=='sync' or mode=='reject' or mode=='partial' or mode=='electric_depot' then finish() end
      end
    """)
    state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    log=tmp_path/'stdout.txt';log.touch();reader=UiLogRequests();output=[]
    lua.globals().print=lambda *v:output.append(' '.join(map(str,v)))
    def flush():
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
    def query(cmd,args):
        t=reader.prepare_build(log,cmd,args)
        assert g.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',t['input'])=='Submitted; inspect log'
        e=lua.globals().forwarded;fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
        fresh['handleEvent'](None,state,'',e['id'],e['name'],e['param']);flush()
        return t,e,reader.read(t['id'])
    if mode=='road_depot':lua.execute('components[300][api.type.ComponentType.VEHICLE_DEPOT].transportModes={[3]=true}')
    if mode=='disabled_rail':lua.execute('components[300][api.type.ComponentType.VEHICLE_DEPOT].transportModes={[7]=false,[8]=false}')
    if mode=='electric_depot':lua.execute('components[300][api.type.ComponentType.VEHICLE_DEPOT].transportModes={[8]=true}')
    if mode=='foreign':lua.execute('components[300][10].player=99')
    if mode=='mu':lua.execute('api.res.modelRep.get(52).metadata.transportVehicle.multipleUnitOnly=true')
    if mode=='bad_quote':lua.globals().price=-1
    models=[52,50] if mode=='nonrail' else [52,999999] if mode=='unknown_model' else [52,53,53]
    _,_,p=query('preview_consist',{'depot':300,'models':models})
    assert lua.globals().calls==0
    if mode in ('foreign','nonrail','unknown_model','mu','bad_quote','road_depot','disabled_rail'):
        assert not p['response']['ok'];return
    assert p['response']['ok'],p
    review=p['response']['result'];assert review['partCount']==3 and review['quotedPartsCost']==300000
    token=review['preview_token']
    if mode=='depot_changed':lua.execute('components[300][api.type.ComponentType.VEHICLE_DEPOT].transportModes={[3]=true}')
    if mode=='expired':lua.globals().now=100
    if mode=='changed':lua.globals().price=210000
    if mode=='resource_changed':lua.execute('api.res.modelRep.getName=function(id)return "changed.mdl" end')
    if mode=='owner_changed':lua.execute('components[300][10].player=99')
    if mode=='stale_epoch':state['v']['uiConstruction']['consistPreviews'][token]['epoch']='old'
    t,e,r=query('commit_consist',{'preview_token':token})
    if mode in ('expired','changed','stale_epoch','resource_changed','owner_changed','depot_changed'):
        assert not r['response']['ok'] and lua.globals().calls==0
        _,_,again=query('commit_consist',{'preview_token':token})
        assert not again['response']['ok'];return
    assert lua.globals().calls==1
    config=lua.globals().last_config
    assert len(config['vehicles'])==3 and list(config['vehicleGroups'].values())==[1,1,1]
    assert len(config['muFileNames'])==0
    assert [part['part']['modelId'] for part in config['vehicles'].values()]==[52,53,53]
    assert all(part['maintenanceState']==1 for part in config['vehicles'].values())
    assert len(config['vehicles'][2]['part']['compartment2loadConfig'])==1
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    fresh['handleEvent'](None,state,'',e['id'],e['name'],e['param']);flush()
    assert lua.globals().calls==1
    if mode in ('deferred','lost'):
        assert r['status']=='pending'
        _,_,blocked=query('commit_consist',{'preview_token':token})
        assert not blocked['response']['ok'] and lua.globals().calls==1
        if mode=='lost':return
        lua.globals().finish();flush();r=reader.read(t['id'])
    assert r['response']['ok']==(mode not in ('reject','partial')),r
    assert (state['v']['uiConstruction']['pending'] is None)==(mode not in ('reject','partial'))
    if mode not in ('reject','partial'):assert len(r['response']['result']['bought'])==1
    _,_,again=query('commit_consist',{'preview_token':token})
    assert not again['response']['ok'] and lua.globals().calls==1

@pytest.mark.parametrize('models',[[],[52],[52]*9,[True,52],[-1,52],[52.5,52],{'1':52,'2':52}])
def test_consist_model_bounds(tmp_path,models):
    with pytest.raises(ValueError):validate_build_arguments('preview_consist',{'depot':300,'models':models})
    g=FakeGame(tmp_path/'game')
    raw='a'*32+' preview_consist '+json.dumps({'depot':300,'models':models})
    result=g.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',raw)
    assert result!='Submitted; inspect log' and len(g.lua.globals().sentCommands)==0
