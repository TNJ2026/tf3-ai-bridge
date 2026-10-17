"""Guarded world adapter against real Lua dispatcher + mocked native API."""
import asyncio
import json
from pathlib import Path

import pytest

from test_ui_consolidated import Channel
from test_no_gui import host, GEN
from tf3_mcp.world_commands import CATALOG, COMMANDS, validate, register

MODULE=Path(__file__).parents[2]/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/world_actions.lua'

SETUP=r'''
local ct=api.type.ComponentType
for _,k in ipairs({'INDUSTRY','STOCK_LIST','TOWN_BUILDING','EMISSION_GRID','EMISSION_EMITTER','CUSTOM_STATE','ANIMAL','MAINTENANCE_COST','SIM_PERSON','BULLDOZER_INFO','WORLD','PLAYER','MODEL_INSTANCE_LIST'})do ct[k]=k end
components[1][ct.GAME_SPEED].speedup=0
components[1][ct.WORLD]={cloudCoverage=.2}
components[2][ct.PLAYER]={}
components[900]={[ct.PLAYER_OWNED]={player=2},[ct.NAME]={name='old'},[ct.INDUSTRY]={stockList=901,construction=902,manualDevelopment=false,closureTimeStamp=100,level=1},
 [ct.TRANSPORT_VEHICLE]={state=2,autoDeparture=true,line=700},[ct.TOWN]={developmentActive=true,initialLandUseCapacities={10,10,10},sizeFactors={1,1,1},levelToCapacityDistributionWeights={{1,1,1,1},{1,1,1,1},{1,1,1,1}}},
 [ct.TOWN_BUILDING]={blockedDevelopment=false},[ct.EMISSION_GRID]={type=0,wind={x=1,y=2}},[ct.EMISSION_EMITTER]={position={x=0,y=0,z=0},radius=10,noisePower=1,pollutionPower=2},
 [ct.CUSTOM_STATE]={state={a=1}},[ct.ANIMAL]={movementType=0,movementSpeed=1,angularSpeed=1,targetChangedElapsed=0,invalidTileElapsed=0},
 [ct.MAINTENANCE_COST]={maintenanceCost=1,accumulatedCost={}},[ct.SIM_PERSON]={happiness=.5},[ct.BULLDOZER_INFO]={locked=false},[ct.MODEL_INSTANCE_LIST]={transf={}},
 [ct.STOCK_LIST]={stocks={{capacity=100,cargoType=1}},modifiers={productivity=1}}}
components[901]={[ct.STOCK_LIST]={stocks={{capacity=100}},modifiers={productivity=1}}}
components[900][ct.CONSTRUCTION]={fileName='::/farm.con',params={}}
api.res.constructionRep.find=function()return 1 end
api.res.constructionRep.get=function()return {isIndustry=true}end
api.type.Vec2f={new=function(x,y)return {x=x,y=y}end}
api.type.Vec3f={new=function(x,y,z)return {x=x,y=y,z=z}end}
api.type.Vec4f={new=function(x,y,z,w)return {x=x,y=y,z=z,w=w}end}
api.type.Mat4f={new=function(...)return {...}end}
api.type.StockList={Modifiers={new=function()return {}end}}
api.engine.Component=api.engine.Component or {}
api.engine.Component.CustomState={new=function()return {}end}
api.engine.Component.EmissionEmitter={new=function()return {}end}
api.type.Date={new=function(y,m,d)return {year=y,month=m,day=d}end}
api.res.modelRep.find=function(name)return 50 end
api.res.modelRep.get=function(id)return {metadata={animal={}}}end
api.res.cargoTypeRep={get=function()return {}end,find=function()return 1 end}
api.cmd.debug={}
function APPLY(cmd)
 local a,n=cmd.args,cmd.native;local c=components[900]
 if n=='makeStockListSetModifiersCmd' then assert(a[1]==900);components[901][ct.STOCK_LIST].modifiers=a[2]
 elseif n=='makeIndustrySetManualDevelopmentCmd' then c[ct.INDUSTRY].manualDevelopment=a[2]
 elseif n=='makeIndustrySetDespawnTimeCmd' then c[ct.INDUSTRY].closureTimeStamp=a[2]
 elseif n=='makeVehicleSetManualDepartureCmd' then c[ct.TRANSPORT_VEHICLE].autoDeparture=not a[2]
 elseif n=='makeTownSetDevelopmentActiveCmd' then c[ct.TOWN].developmentActive=a[2]
 elseif n=='makeTownSetInitialLandUseCapacitiesCmd' then c[ct.TOWN].initialLandUseCapacities=a[2]
 elseif n=='makeTownUpdateSizeCmd' then c[ct.TOWN].sizeFactors=a[2]
 elseif n=='makeTownCustomDistributionWeightsCmd' then c[ct.TOWN].levelToCapacityDistributionWeights=a[2]
 elseif n=='makeTownBuildingSetBlockedDevelopmentCmd' then c[ct.TOWN_BUILDING].blockedDevelopment=a[2]
 elseif n=='makeGameSetCalendarSpeedCmd' then components[1][ct.GAME_SPEED].millisPerDay=a[1]
 elseif n=='makeGameSetDateCmd' then api.engine.util.getCalendarDate=function()return a[1]end
 elseif n=='makeGameSetTimeOfDayCmd' then components[1][ct.GAME_TIME].timeOfDaySec=a[1]
 elseif n=='makeGameSetCloudCoverageCmd' then components[1][ct.WORLD].cloudCoverage=a[1]
 elseif n=='makeWorldChangeWindCmd' then c[ct.EMISSION_GRID].wind=a[2]
 elseif n=='makeEntitySetNameCmd' then assert(a[3]==true);c[ct.NAME].name=a[2]
 elseif n=='makeEntitySetPlayerCmd' then c[ct.PLAYER_OWNED].player=a[2]
 elseif n=='makeWorldSetBulldozableCmd' then c[ct.BULLDOZER_INFO].locked=not a[2]
 elseif n=='makeCustomEntityUpdateStateCmd' then c[ct.CUSTOM_STATE].state=a[2]
 elseif n=='makeCustomEntityDestroyCmd' then components[900]=nil
 elseif n=='debug.makeMaintenanceCostUpdateCmd' then c[ct.MAINTENANCE_COST].maintenanceCost=a[2]
 elseif n=='debug.makeSimPersonSetHappiness' then c[ct.SIM_PERSON].happiness=a[2]
 elseif n=='makeStockListSetStocksCargoTypeCmd' then c[ct.STOCK_LIST].stocks[1].cargoType=a[3]
 elseif n=='debug.makeComponentExchangeCmd' then c[ct.EMISSION_EMITTER]=a[2]
 end
 components[999]={[ct.CUSTOM_STATE]={state={}}}
end
api.cmd.sendCommand=function(cmd,cb)
 LAST=cmd
 if THROW then error('dispatch lost')end
 if DELAY then DEFERRED={cmd=cmd,cb=cb};return end
 if not NO_APPLY and not REJECT then APPLY(cmd)end
 cb({resultEntity=999,resultProposal={toAdd={},toRemove={}},resultCollidingSubconstructions={}},not REJECT)
end
'''


def args(action):
    vals=dict(entity=900,productivity=5,manual=True,timestamp=1000,active=False,capacities=[20,20,20],
              factors=[2,2,2],update_buildings=False,weights=[[1,2,3,4]]*3,blocked=True,millis_per_day=3000,
              year=2000,month=2,day=29,seconds=100,coverage=.6,x=5,y=6,noise_power=5,pollution_power=6,
              noise_radius=10,pollution_radius=20,name='new',player=2,value=False,stock_ids=[0],cargo=2,
              remaining_time=0,model='::/model.mdl',state={'a':2},columns=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[5,6,7,1]],
              look_x=1,look_y=0,movement_type=0,target_elapsed=0,invalid_elapsed=0,speed=5,angular_speed=1,
              r=1,g=0,b=0,towns=[900],amount=10,reset_accumulated=False,happiness=.9,stock_id=0,steps=1,
              entries=[['test',10,False]],try_slots=2,keep_slots=1,develop_streets=True,upgrade_buildings=True,
              keep=True,seed='test',keep_assets=True,source_vehicle=900,source_entity=900)
    if action=='debug_stock_amount':vals['cargo']='::/cargo/FOOD.cargo'
    if action=='debug_person_state':vals['state']=1
    if action=='debug_clear_logbooks':vals['towns']=True
    return {k:vals[k] for k in CATALOG[action]['fields']}


def channel(tmp_path):
    c=Channel(tmp_path,SETUP)
    module=c.lua.execute(MODULE.read_text(encoding='utf-8'))
    c.lua.globals().worldModule=module
    c.lua.execute('ug_require=function(name)assert(name=="tnj_tf3_ai_bridge::/tf3_mcp_bridge/world_actions.lua");return worldModule end')
    for spec in CATALOG.values():
        name=spec['native']; table=c.lua.globals().api.cmd.debug if name.startswith('debug.') else c.lua.globals().api.cmd
        table[name.split('.')[-1]]=c.lua.eval('function(name)return function(...)return {native=name,args={...}}end end')(name)
    return c


@pytest.mark.parametrize('action',CATALOG)
def test_every_catalog_action_has_consistent_schema_and_safe_dispatch(tmp_path,action):
    c=channel(tmp_path);p=args(action)
    result=c.query('preview_world_action',{'action':action,'parameters':p})
    assert result['ok'],result
    if CATALOG[action]['blocked']:
        assert result['result']['blocked'] and 'preview_token' not in result['result']
        assert c.lua.globals().dispatches==0
        return
    token=result['result']['preview_token']
    result=c.query('commit_world_action',dict(preview_token=token,backup_save='test_backup'))
    assert result['ok'],result
    assert result['result']['verified'] is False
    assert c.lua.globals().dispatches==1
    assert c.lua.globals().LAST.native==CATALOG[action]['native']
    result=c.query('get_world_action_operation',{'operation_id':token})
    assert result['ok'],result
    assert result['result']['status'] in {'verified','accepted_unverified'},result
    assert c.state['v']['uiConstruction']['pending'] is None
    assert not c.query('commit_world_action',dict(preview_token=token,backup_save='test_backup'))['ok']
    assert c.lua.globals().dispatches==1


@pytest.mark.parametrize('action,field',[('town_development','developmentActive'),('town_initial_capacities','initialLandUseCapacities'),('town_size','sizeFactors')])
def test_town_actions_ignore_unrelated_unreadable_distribution(tmp_path,action,field):
    c=channel(tmp_path)
    c.lua.execute('components[900][api.type.ComponentType.TOWN].levelToCapacityDistributionWeights=function()end')
    p=c.query('preview_world_action',{'action':action,'parameters':args(action)})
    assert p['ok'],p
    assert set(p['result']['before']['component'])=={field}
    token=p['result']['preview_token']
    assert c.query('commit_world_action',dict(preview_token=token,backup_save='test_backup'))['ok']
    r=c.query('get_world_action_operation',{'operation_id':token})
    assert r['result']['verified'],r


@pytest.mark.parametrize('mode',['DELAY','THROW','NO_APPLY'])
def test_unknown_or_mismatched_result_stays_pending(tmp_path,mode):
    c=channel(tmp_path)
    token=c.query('preview_world_action',{'action':'industry_productivity','parameters':args('industry_productivity')})['result']['preview_token']
    c.lua.globals()[mode]=True
    assert c.query('commit_world_action',dict(preview_token=token,backup_save='backup'))['ok']
    r=c.query('get_world_action_operation',{'operation_id':token})
    assert not r['result']['verified'] and c.state['v']['uiConstruction']['pending']
    assert not c.query('preview_world_action',{'action':'industry_productivity','parameters':args('industry_productivity')})['ok']
    if mode=='DELAY':
        c.lua.execute('APPLY(DEFERRED.cmd);DEFERRED.cb({},true)')
        assert c.query('get_world_action_operation',{'operation_id':token})['result']['verified']
        assert c.state['v']['uiConstruction']['pending'] is None


def test_rejected_callback_and_stale_preview(tmp_path):
    c=channel(tmp_path)
    def preview():return c.query('preview_world_action',{'action':'industry_productivity','parameters':args('industry_productivity')})['result']['preview_token']
    t=preview();c.lua.execute('components[901][api.type.ComponentType.STOCK_LIST].modifiers.productivity=2')
    assert not c.query('commit_world_action',dict(preview_token=t,backup_save='backup'))['ok']
    assert c.lua.globals().dispatches==0
    t=preview();c.lua.globals().REJECT=True
    assert c.query('commit_world_action',dict(preview_token=t,backup_save='backup'))['ok']
    assert c.query('get_world_action_operation',{'operation_id':t})['result']['status']=='rejected'


def test_rejected_but_changed_keeps_pending(tmp_path):
    c=channel(tmp_path)
    t=c.query('preview_world_action',{'action':'industry_productivity','parameters':args('industry_productivity')})['result']['preview_token']
    c.lua.globals().REJECT=True
    assert c.query('commit_world_action',dict(preview_token=t,backup_save='backup'))['ok']
    c.lua.execute('components[901][api.type.ComponentType.STOCK_LIST].modifiers.productivity=7')
    r=c.query('get_world_action_operation',{'operation_id':t})['result']
    assert r['status']=='rejected_but_state_changed'
    assert c.state['v']['uiConstruction']['pending']


def test_float_readback_tolerates_native_precision(tmp_path):
    c=channel(tmp_path)
    t=c.query('preview_world_action',{'action':'cloud_coverage','parameters':args('cloud_coverage')})['result']['preview_token']
    assert c.query('commit_world_action',dict(preview_token=t,backup_save='backup'))['ok']
    c.lua.execute('components[1][api.type.ComponentType.WORLD].cloudCoverage=0.600000024')
    assert c.query('get_world_action_operation',{'operation_id':t})['result']['verified']


def test_receiver_validates_nested_payload_without_host(tmp_path):
    c=channel(tmp_path)
    p=args('custom_entity_transform');p['columns'][3][3]=0
    raw='a'*32+' preview_world_action '+json.dumps({'action':'custom_entity_transform','parameters':p})
    result=c.game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',raw)
    assert result == 'Result logged' and c.lua.globals().dispatches==0
    assert 'forwarded' not in list(c.lua.globals())
    payload=''.join(line.split(' hex=',1)[1] for line in c.output if ' hex=' in line)
    response=json.loads(bytes.fromhex(payload))
    assert response['rejectedBeforeDispatch'] and 'affine' in response['error']


def test_receiver_missing_native_and_expired_token(tmp_path):
    c=channel(tmp_path)
    t=c.query('preview_world_action',{'action':'industry_productivity','parameters':args('industry_productivity')})['result']['preview_token']
    c.state['v']['uiConstruction']['worldActionPreviews'][t]['created']-=61
    assert not c.query('commit_world_action',dict(preview_token=t,backup_save='backup'))['ok']
    c.lua.execute('api.cmd.makeStockListSetModifiersCmd=nil')
    assert not c.query('preview_world_action',{'action':'industry_productivity','parameters':args('industry_productivity')})['ok']
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('action,key,bad',[
 ('game_date','day',30),('calendar_speed','millis_per_day',0),('cloud_coverage','coverage',2),
 ('industry_productivity','productivity',float('nan')),('entity_name','name',''),
 ('custom_entity_create','model','C:/a.mdl'),('stock_discard','stock_ids',[0,0]),
 ('industry_manual_development','manual',1),('debug_simulation_steps','steps',101),
])
def test_invalid_inputs(action,key,bad):
    p=args(action);p[key]=bad
    with pytest.raises(ValueError):validate('preview_world_action',dict(action=action,parameters=p))


@pytest.mark.parametrize('cmd',COMMANDS)
def test_old_receiver_cannot_publish(host,cmd):
    a={} if cmd=='list_world_actions' else {'action':'industry_productivity','parameters':args('industry_productivity')} if cmd=='preview_world_action' else {'preview_token':'token','backup_save':'backup'} if cmd=='commit_world_action' else {'operation_id':'token'}
    with pytest.raises(ValueError,match='worldActionsVersion'):
        host.send(cmd,a,kind='build',expected_session='session')
    assert not host.ledger.exists()
    assert (host.mod/'no_gui'/GEN/'1.lua').read_bytes()==b'return ""\n'


def test_embedded_catalog_matches_python():
    embedded=MODULE.read_text(encoding='utf-8').split('[==[',1)[1].split(']==]',1)[0]
    expected={k:{a:b for a,b in s.items() if b is not None}for k,s in CATALOG.items()}
    assert json.loads(embedded)==expected


@pytest.mark.parametrize('failure',[None,'backup','version','running'])
def test_public_commit_backup_and_independent_read(tmp_path,failure):
    from types import SimpleNamespace
    calls=[];tools={}
    class MCP:
        def tool(self):
            def add(fn):tools[fn.__name__]=fn;return fn
            return add
    class Client:
        requests=SimpleNamespace(directory=tmp_path)
        async def status(self):return {'receiver':{'worldActionsVersion':0 if failure=='version' else 1}}
        async def call(self,name,a):
            calls.append(name)
            if name=='get_game_state':return {'speedup':1 if failure=='running' else 0}
            if name=='save_game':return {'verified':failure!='backup'}
            if name=='commit_world_action':return {'operation_id':'token'}
            return {'verified':True}
    register(MCP(),None,lambda:Client())
    if failure:
        with pytest.raises(ValueError):asyncio.run(tools['commit_world_action']('token'))
        assert 'commit_world_action' not in calls
    else:
        assert asyncio.run(tools['commit_world_action']('token'))['verified']
        assert calls==['get_game_state','save_game','commit_world_action','get_world_action_operation']


def test_module_load_failure_returns_rejection_without_stopping_channel(tmp_path):
    c=channel(tmp_path)
    c.lua.execute("ug_require=function(path)error('module unavailable')end")
    ticket=c.reader.prepare_build(c.log,'list_world_actions',{})
    result=c.game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])
    assert result == 'Result logged'
    payload=''.join(line.split(' hex=',1)[1] for line in c.output if ' hex=' in line)
    response=json.loads(bytes.fromhex(payload))
    assert not response['ok'] and response['rejectedBeforeDispatch']
    assert response['code']=='world_action_preflight_rejected'
    assert 'module unavailable' in response['error']
    assert c.lua.globals().dispatches==0


def test_world_catalog_accepts_callable_native_tables(tmp_path):
    c=channel(tmp_path)
    c.lua.execute("""
      local function wrap(t)
       for k,v in pairs(t)do
        if type(v)=='function' then
         local f=v;t[k]=setmetatable({}, {__metatable='native',__call=function(_,...)return f(...)end})
        elseif type(v)=='table' then wrap(v)end
       end
      end
      wrap(api.cmd)
    """)
    catalog=c.query('list_world_actions',{})
    assert catalog['ok']
    assert all(row['available'] for row in catalog['result']['actions'].values())
    preview=c.query('preview_world_action',{'action':'industry_productivity','parameters':args('industry_productivity')})
    assert preview['ok'],preview
    token=preview['result']['preview_token']
    result=c.query('commit_world_action',{'preview_token':token,'backup_save':'backup'})
    assert result['ok'],result
    assert c.query('get_world_action_operation',{'operation_id':token})['result']['verified']


def test_paused_engine_ticks_do_not_invalidate_calendar_preview(tmp_path):
    c=channel(tmp_path)
    p=c.query('preview_world_action',{'action':'calendar_speed','parameters':{'millis_per_day':5000}})
    assert p['ok'],p
    assert 'tickCount' not in p['result']['before']['game']
    # Every query loads the real bridge anew; engine ticks may change between callbacks.
    c.lua.execute('components[1][api.type.ComponentType.GAME_TIME].tickCount=99999')
    r=c.query('commit_world_action',{'preview_token':p['result']['preview_token'],'backup_save':'backup'})
    assert r['ok'],r

@pytest.mark.parametrize('field,value',[('gameTime',999999),('timeOfDaySec',7200)])
def test_real_world_state_change_still_rejects_preview(tmp_path,field,value):
    c=channel(tmp_path)
    p=c.query('preview_world_action',{'action':'calendar_speed','parameters':{'millis_per_day':5000}})
    c.lua.execute('components[1][api.type.ComponentType.GAME_TIME][...] = select(2,...)',field,value)
    r=c.query('commit_world_action',{'preview_token':p['result']['preview_token'],'backup_save':'backup'})
    assert not r['ok'] and 'Target state changed' in r['error']
    assert c.lua.globals().dispatches==0
