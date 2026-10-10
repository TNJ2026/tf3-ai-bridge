"""New-channel safety/dispatch tests, with native API mocked (not live acceptance)."""
import json
import pytest
from test_e2e import FakeGame, SCRIPT
from test_facilities import FIXTURE as FACILITY
from test_town_cargo_needs import FIXTURE as TOWN
from test_loans import FIXTURE as LOAN
from test_subventions import FIXTURE as SUBVENTION
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments


class Channel:
    def __init__(self, tmp_path, fixture=''):
        self.game = FakeGame(tmp_path / 'game')
        self.lua = self.game.lua
        self.lua.execute(fixture)
        self.lua.execute('''
          local send,make=api.cmd.sendCommand,api.cmd.makeScriptingSendEventCmd
          dispatches=0
          api.cmd.makeScriptingSendEventCmd=function(src,id,name,param)
           if id=='tnj_bridge_build' then return {event=true,id=id,name=name,param=param} end
           return make(src,id,name,param)
          end
          api.cmd.sendCommand=function(cmd,cb)
           if cmd.event then forwarded=cmd;return end
           dispatches=dispatches+1
           send(cmd,cb)
          end
        ''')
        self.state = self.lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
        self.log = tmp_path / 'stdout.txt'; self.log.touch()
        self.reader = UiLogRequests(); self.output = []
        self.lua.globals().print = lambda *v: self.output.append(' '.join(map(str, v)))

    def query(self, command, args, epoch=None):
        ticket = self.reader.prepare_build(self.log, command, args)
        r = self.game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])
        assert r == 'Submitted; inspect log', r
        event = self.lua.globals().forwarded
        param = event['param']
        if epoch:
            obj = json.loads(param); obj['facilityEpoch'] = epoch; param = json.dumps(obj)
        fresh = self.lua.execute(SCRIPT.read_text(encoding='utf-8'), name="test/bridge.script.lua")
        fresh['handleEvent'](None,self.state,'',event['id'],event['name'],param)
        with self.log.open('a',encoding='utf-8') as f: f.write('\n'.join(self.output)+'\n')
        self.output.clear()
        return self.reader.read(ticket['id'])['response']


@pytest.mark.parametrize('fixture,preview,args,commit,read', [
    (TOWN,'preview_town_cargo_needs',{'town':100,'commercial':[3]},'commit_town_cargo_needs','get_town_cargo_operation'),
    (LOAN,'preview_loan',{'action':'borrow','offer_type':'Small'},'commit_loan','get_loan_operation'),
])
@pytest.mark.parametrize('mode',['ok','delay','lost','stale','wrong_kind'])
def test_workflow_tokens_and_unknown_outcomes(tmp_path,fixture,preview,args,commit,read,mode):
    c=Channel(tmp_path,fixture)
    p=c.query(preview,args); assert p['ok'],p
    token=p['result']['preview_token']
    if mode=='stale':
        r=c.query(commit,{'preview_token':token},epoch='different-session')
        assert not r['ok'] and c.lua.globals().dispatches==0; return
    if mode=='wrong_kind':
        other='commit_loan' if commit!='commit_loan' else 'commit_industry'
        r=c.query(other,{'preview_token':token})
        assert not r['ok'] and c.lua.globals().dispatches==0; return
    if mode=='delay': c.lua.globals().DELAY=True
    if mode=='lost': c.lua.execute('THROW=true;DISPATCH_ERROR=true')
    result=c.query(commit,{'preview_token':token}); assert result['ok'],result
    assert c.lua.globals().dispatches==1
    ledger=c.state['v']['uiConstruction']
    if mode=='ok':
        assert result['result']['verified'] and ledger['pending'] is None
        assert c.query(read,{'operation_id':token})['result']['verified']
    else:
        assert ledger['pending']
        assert not c.query(preview,args)['ok']
        if mode=='delay':
            if commit=='commit_loan': c.lua.execute('DELIVER(PENDING)')
            else: c.lua.execute('components[PENDING.id][2].cargoNeeds=PENDING.weighted')
            assert c.query(read,{'operation_id':token})['result']['verified']
            assert ledger['pending'] is None
    assert not c.query(commit,{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==1


@pytest.mark.parametrize('preview,args',[
    ('preview_facility_parameter',{'entity':8000,'key':'size','value':2}),
    ('preview_facility_module',{'entity':8000,'slot':11,'resource':'::/warehouses/b.module'}),
])
def test_facility_edit_uses_existing_guarded_workflow(tmp_path,preview,args):
    c=Channel(tmp_path,FACILITY)
    p=c.query(preview,args); assert p['ok'],p
    assert p['result']['check']['structural_only']
    assert c.lua.globals().dispatches==0
    token=p['result']['preview_token']
    r=c.query('commit_facility',{'preview_token':token}); assert r['ok'] and r['result']['verified'],r
    params=r['result']['config']['params']
    if preview.endswith('parameter'): assert params['size']==2
    else: assert params['modules']['11']['name']=='::/warehouses/b.module'
    assert c.lua.globals().dispatches==1
    assert not c.query('commit_facility',{'preview_token':token})['ok']


MU_FIXTURE='''
components[300][api.type.ComponentType.VEHICLE_DEPOT].transportModes={[7]=true}
api.res.multipleUnitRep={getAll=function()return {[3]='mu.unit'}end,
 getName=function(id)return 'mu.unit'end,
 get=function(id)return {name='native MU',vehicles={{name=api.res.modelRep.getName(52),forward=true},{name=api.res.modelRep.getName(52),forward=false}}}end}
api.engine.util.vehicle={getPartPrice=function(part)return 100 end}
api.res.modelRep.get(52).metadata.transportVehicle.multipleUnitOnly=true
local buy=api.cmd.makeVehicleBuyCmd
api.cmd.makeVehicleBuyCmd=function(player,depot,config)MU_CONFIG=config;return buy(player,depot,config)end
'''


@pytest.mark.parametrize('mode',['ok','changed','unknown','bad_part'])
def test_fixed_mu_order_groups_and_orientation(tmp_path,mode):
    c=Channel(tmp_path,MU_FIXTURE)
    if mode=='bad_part': c.lua.execute("api.res.multipleUnitRep.get=function()return {vehicles={{name='missing',forward=true}}}end")
    p=c.query('preview_multiple_unit',{'depot':300,'resource':'missing' if mode=='unknown' else 'mu.unit'})
    if mode in ('unknown','bad_part'):
        assert not p['ok'] and c.lua.globals().dispatches==0;return
    assert p['ok'],p
    token=p['result']['preview_token']
    if mode=='changed':c.lua.execute('api.engine.util.vehicle.getPartPrice=function()return 150 end')
    r=c.query('commit_consist',{'preview_token':token})
    if mode=='changed': assert not r['ok'] and c.lua.globals().dispatches==0;return
    assert r['ok'],r
    config=c.lua.globals().MU_CONFIG
    assert list(config['vehicleGroups'].values())==[2]
    assert list(config['muFileNames'].values())==['mu.unit']
    assert [x['part']['reversed'] for x in config['vehicles'].values()]==[False,True]
    assert not c.query('commit_consist',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==1


@pytest.mark.parametrize('args',[
 {'via':[{'node':1}]}, {'via':[{'x':1,'y':2}]*4},
 {'start':{'node':True}}, {'template':True},
])
def test_network_rejects_unbounded_or_ambiguous_input(args):
    value={'start':{'x':0,'y':0},'end':{'x':100,'y':0},'template':'road'};value.update(args)
    with pytest.raises(ValueError): validate_build_arguments('preview_network',value)


NETWORK_FIXTURE='''
local iterate=api.engine.forEachEntityWithComponent
api.engine.forEachEntityWithComponent=function(fn,ct)
 assert(ct~=api.type.ComponentType.BASE_EDGE and ct~=api.type.ComponentType.BASE_NODE,'Cannot loop over this component type')
 return iterate(fn,ct)
end
api.engine.system.streetSystem.getNode2SegmentMap=function()
 local map={}
 for id,c in pairs(components) do local e=c[api.type.ComponentType.BASE_EDGE]
  if e then for _,node in ipairs({e.node0,e.node1}) do map[node]=map[node] or {};table.insert(map[node],id) end end
 end
 return map
end
NOW=100;os.clock=function()return NOW end
api.type.ComponentType.TRANSPORT_NETWORK=998
local rep=api.res.streetTemplateRep
local get=rep.get
rep.get=function(id)local t=get(id);t.roadType=NETWORK_RAIL and api.type.enum.RoadType.TRACK or api.type.enum.RoadType.STREET;return t end
local send=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 if LOST then return end
 send(cmd,function(...)
  for _,components in pairs(components) do
   if components[api.type.ComponentType.BASE_EDGE] or components[api.type.ComponentType.BASE_NODE] then
    components[api.type.ComponentType.TRANSPORT_NETWORK]={edges={},nodes={}}
   end
  end
  cb(...)
 end)
end
'''


@pytest.mark.parametrize('rail',[False,True])
@pytest.mark.parametrize('mode',['ok','expired','lost','curve','sharp','too_long','changed'])
def test_network_construction_is_bounded_and_single_use(tmp_path,rail,mode):
    c=Channel(tmp_path,NETWORK_FIXTURE);c.lua.globals().NETWORK_RAIL=rail
    args={'start':{'x':700,'y':700},'end':{'x':800,'y':700},'template':'town/town_old_small'}
    if mode=='curve':args.update(via=[{'x':750,'y':710}])
    if mode=='sharp':args.update(via=[{'x':850,'y':700}])
    if mode=='too_long':args['end']['x']=1100
    p=c.query('preview_network',args)
    if mode in ('sharp','too_long'):
        assert not p['ok'] and c.lua.globals().dispatches==0;return
    assert p['ok'] and p['result'].get('preview_token'),p
    assert not p['result']['serviceConnectivityVerified']
    token=p['result']['preview_token']
    if mode=='expired':c.lua.globals().NOW=161
    if mode=='changed':c.lua.execute('api.res.streetTemplateRep.get=function()return {roadType=99}end')
    if mode=='lost':c.lua.globals().LOST=True
    r=c.query('commit_network',{'preview_token':token})
    if mode in ('expired','changed'):
        assert not r['ok'] and c.lua.globals().dispatches==0
    elif mode=='lost':
        assert r['ok'] and not r['result']['built'] and c.state['v']['uiConstruction']['pending']
    else:
        assert r['ok'] and r['result']['verified'],r
        assert len(r['result']['edges'])==(2 if mode=='curve' else 1)
        for entity in r['result']['edges']:
            edge=c.lua.globals().components[entity][c.lua.globals().api.type.ComponentType.BASE_EDGE]
            assert edge['roadType']==(0 if rail else 1)
        assert not c.state['v']['uiConstruction']['pending']
    before=c.lua.globals().dispatches
    assert not c.query('commit_network',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==before


@pytest.mark.parametrize('mode',['ok','changed','lost'])
def test_road_replacement_guard_and_receipt(tmp_path,mode):
    c=Channel(tmp_path)
    edge=c.lua.globals().STREET_AB
    # Fixture exposes the actual edge global under STREET_EDGE.
    if edge is None:
        edge=next(entity for entity,cs in c.lua.globals().components.items()
                  if cs[c.lua.globals().api.type.ComponentType.BASE_EDGE] is not None)
    p=c.query('preview_road_upgrade',{'edge':edge,'street_type':'town/town_old_medium'})
    assert p['ok'] and p['result']['validation']=='structural_only',p
    token=p['result']['preview_token']
    if mode=='changed':c.lua.globals().components[edge][c.lua.globals().api.type.ComponentType.BASE_EDGE]['node0']=999
    if mode=='lost':c.lua.execute('api.cmd.sendCommand=function(cmd,cb) if cmd.event then forwarded=cmd else dispatches=dispatches+1 end end')
    r=c.query('commit_edge_edit',{'preview_token':token})
    if mode=='changed':assert not r['ok'] and c.lua.globals().dispatches==0
    elif mode=='lost':assert r['ok'] and not r['result']['applied'] and c.state['v']['uiConstruction']['pending']
    else:assert r['ok'] and r['result']['verified'],r
    before=c.lua.globals().dispatches
    assert not c.query('commit_edge_edit',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==before


def test_cleanup_only_current_channel_objects_and_no_replay(tmp_path):
    c=Channel(tmp_path,NETWORK_FIXTURE)
    old=next(entity for entity,cs in c.lua.globals().components.items()
             if cs[c.lua.globals().api.type.ComponentType.BASE_EDGE] is not None)
    assert not c.query('preview_test_removal',{'entity':old})['ok']
    p=c.query('preview_network',{'start':{'x':700,'y':700},'end':{'x':800,'y':700},'template':'town/town_old_small'})
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    entity=r['result']['edges'][0]
    preview=c.query('preview_test_removal',{'entity':entity});assert preview['ok'],preview
    assert preview['result']['validation']=='structural_only'
    args={'preview_token':preview['result']['preview_token']}
    removed=c.query('commit_test_removal',args)
    assert removed['ok'] and removed['result']['verified'],removed
    assert c.lua.globals().components[entity] is None
    assert not c.query('commit_test_removal',args)['ok']
    assert c.lua.globals().dispatches==2


def test_targeted_consumption_and_delivery_reads(tmp_path):
    c=Channel(tmp_path, '''
     api.type.ComponentType.STOCK_LIST=999;components[900]={[999]={stocks={}}}
     api.res.cargoTypeRep={getAll=function()return {[0]='passengers',[6]='fish'}end}
     api.util={getDefaultYearDuration=function()return 10000 end}
     api.engine.util.stock={getCargoConsumedPerYear=function(id,cargo)assert(id==900 and cargo==6);return 12 end,
      getCargoMaxConsumptionPerYear=function()return 30 end}
     api.engine.util.town={getTownDeliveriesStats=function(town,interval,perLine,perCargo)
      assert(town==100 and interval==5000 and perLine and perCargo);return {[400]={[6]={2,12}}} end}
    ''')
    r=c.query('get_stock_activity',{'stock_list':900,'cargo':6})
    assert r['ok'] and r['result']['annualConsumed']==12
    assert not c.query('get_stock_activity',{'stock_list':100,'cargo':6})['ok']
    r=c.query('get_town_deliveries',{'town':100})
    assert r['ok'] and r['result']['items']==[{'line':400,'cargo':6,'late':2,'total':12}]
    assert c.lua.globals().dispatches==0


TERRAIN_FIXTURE='''
NOW=100;os.clock=function()return NOW end
REV=1;HEIGHTS={}
local CT=api.type.ComponentType;CT.TERRAIN=201;CT.MODEL_INSTANCE_LIST=202
components[1][CT.TERRAIN]={waterLevel=0}
api.engine.terrain.getBaseResolution=function()return {x=4,y=4,z=.05}end
api.engine.terrain.getBoundingBox=function()return {min={x=-1000,y=-1000},max={x=1000,y=1000}}end
api.engine.terrain.getBaseHeightAt=function(p)return HEIGHTS[p.x..':'..p.y] or 10 end
api.engine.terrain.getHeightAt=function(p)return api.engine.terrain.getBaseHeightAt(p)end
api.engine.terrain.isOnWater=function()return false end
api.engine.terrain.getTerrainEntityRevisions=function()return {[1]={num={REV,0,0}}}end
api.engine.util.octree.findEntitiesInCircle=function()return {}end
api.type.GridVec2f={new=function(x,y,w,h,value)return {x0=x,y0=y,width=w,height=h,value=value.x}end}
api.type.Proposal={new=function()return {terrain={}}end}
api.cmd.makeWorldBuildProposalCmd=function(p,ctx,ignore,player)assert(ignore==false and player==true);return p end
api.cmd.sendCommand=function(p,cb)
 if LOST then return end
 local g=p.terrain.baseHeightMod
 for x=g.x0,g.x0+g.width-1 do for y=g.y0,g.y0+g.height-1 do HEIGHTS[(x*4)..':'..(y*4)]=g.value end end
 REV=REV+1;cb({},true)
end
'''


@pytest.mark.parametrize('mode',['ok','lost','changed'])
def test_terrain_one_shot_workflow_keeps_backup_and_unknown_guards(tmp_path,mode):
    c=Channel(tmp_path,TERRAIN_FIXTURE)
    p=c.query('preview_flatten_terrain',{'bounds':{'min':{'x':700,'y':700},'max':{'x':708,'y':708}},'target_height':10.1})
    assert p['ok'] and p['result'].get('preview_token'),p
    token=p['result']['preview_token']
    if mode=='lost':c.lua.globals().LOST=True
    if mode=='changed':c.lua.globals().REV=2
    r=c.query('commit_flatten_terrain',{'preview_token':token,'backup_save':'verified_test_backup'})
    if mode=='changed': assert not r['ok'] and c.lua.globals().dispatches==0;return
    assert r['ok'],r
    assert r['result']['verified']==(mode=='ok')
    assert bool(c.state['v']['uiConstruction']['pending'])==(mode=='lost')
    if mode=='ok': assert c.query('get_terrain_operation',{'operation_id':token})['result']['verified']
    before=c.lua.globals().dispatches
    assert not c.query('commit_flatten_terrain',{'preview_token':token,'backup_save':'verified_test_backup'})['ok']
    assert c.lua.globals().dispatches==before


@pytest.mark.parametrize('bounds',[
 {'min':{'x':True,'y':0},'max':{'x':1,'y':1}},
 {'min':{'x':0},'max':{'x':1,'y':1}},
 {'min':{'x':0,'y':0},'max':{'x':0,'y':1}},
 {'min':{'x':0,'y':0},'max':{'x':1,'y':float('nan')}},
])
def test_terrain_host_bounds_validation(bounds):
    with pytest.raises(ValueError): validate_build_arguments('preview_flatten_terrain',{'bounds':bounds,'target_height':0})


@pytest.mark.parametrize('mode',['ok','changed','delayed','lost'])
def test_subvention_durable_uid_and_terms(tmp_path,mode):
    c=Channel(tmp_path,SUBVENTION+'''
     os.clock=function()return 100 end
     api.cmd.sendCommand=function(cmd,cb)
      COMPLETE=function()
       local row=table.remove(SUB.proposedSubventions,1);row.acceptedTime=1000000
       SUB.activeSubventions[#SUB.activeSubventions+1]=row
      end
      if not DELAY and not LOST then COMPLETE() end
      if not LOST then cb({},true)end
     end
    ''')
    p=c.query('preview_subvention',{'uid':7001});assert p['ok'],p
    assert not p['result']['networkFeasibilityVerified']
    token=p['result']['preview_token']
    if mode=='changed':c.lua.execute('SUB.proposedSubventions[1].data.expireDuration=10')
    if mode=='delayed':c.lua.globals().DELAY=True
    if mode=='lost':c.lua.globals().LOST=True
    r=c.query('commit_subvention',{'preview_token':token})
    if mode=='changed':assert not r['ok'] and c.lua.globals().dispatches==0;return
    assert r['ok'],r
    assert r['result']['verified']==(mode=='ok')
    if mode=='delayed':
        c.lua.globals().COMPLETE()
        assert c.query('get_subvention_operation',{'operation_id':token})['result']['verified']
        assert c.state['v']['uiConstruction']['pending'] is None
    assert not c.query('preview_subvention',{'uid':7001})['ok']
    assert not c.query('commit_subvention',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==1


def test_large_facility_layout_is_bounded_and_metadata_omitted(tmp_path):
    c=Channel(tmp_path,FACILITY+'''
     PARAMS.modules={}
     components[8000][api.type.ComponentType.CONSTRUCTION].slotConfig.storage.maxModules=300
     for i=1,200 do PARAMS.modules[i]={name='::/warehouses/a.module',variant=0,metadata={huge=string.rep('x',2000)}}end
    ''')
    r=c.query('get_facility_layout',{'entity':8000,'offset':0,'limit':20})
    assert r['ok'],r
    v=r['result'];assert v['moduleCount']==200 and v['hasMore']
    assert len(v['params']['modules'])==20 and len(json.dumps(v))<10000
    modules=v['params']['modules']
    assert all('metadata' not in m for m in (modules if isinstance(modules,list) else modules.values()))
    p=c.query('preview_facility_parameter',{'entity':8000,'key':'size','value':2})
    # A large preview must also remain bounded (it otherwise blocks the commit).
    assert p['ok'],p
    assert p['result']['parameterModuleCount']==200 and p['result']['parametersHasMore']
    committed=c.query('commit_facility',{'preview_token':p['result']['preview_token']})
    assert committed['ok'] and committed['result']['verified'],committed
    assert committed['result']['config']['hasMore']


@pytest.mark.parametrize('mode',['ok','out_of_range','changed','native_ok','native_changed'])
def test_terminal_change_preserves_loads_and_checks_native_identity(tmp_path,mode):
    c=Channel(tmp_path,'''
     components[700]={[3]={customFilters=true,reservationPriority=1,stops={}},[10]={player=2}}
     for i=1,2 do components[700][3].stops[i]={stationGroup=199+i,station=0,terminal=0,
      waypoints={},alternativeTerminals={},maxAdditionalWaitingTime=3,
      stopConfig={load={false,true},maxLoad={.2,.3},forceUnload=false,destroyForConfigChange=false,destroyForRefresh=false}} end
     api.type.ComponentType.STATION=111
     components[210][111]={terminals={{vehicleNodeId={entity=210,index=0}},{vehicleNodeId={entity=210,index=1}}}}
     api.type.Line.StopConfig={new=function()return {}end}
     api.res.cargoTypeRep={getAll=function()return {[0]='PASSENGERS',[1]='COAL'}end}
     api.cmd.makeLineUpdateCmd=function(id,config)return {id=id,config=config}end
     api.cmd.sendCommand=function(cmd,cb)components[cmd.id][3]=cmd.config;cb({},true)end
    ''')
    if mode.startswith('native_'):
        from test_ui_network_native_snapshots import NativeRecord
        node=NativeRecord(entity=210,index=1)
        c.lua.globals().native_node=lambda:node
        c.lua.execute('components[210][111].terminals[2]={vehicleNodeId=native_node(),personNodes={native_node()}}')
    p=c.query('preview_line_terminal',{'line':700,'stop_index':0,'station_index':0,'terminal':2 if mode=='out_of_range' else 1})
    if mode=='out_of_range':assert not p['ok'] and c.lua.globals().dispatches==0;return
    assert p['ok'],p
    if mode=='changed':c.lua.execute('components[210][111].terminals[2].vehicleNodeId.index=2')
    if mode=='native_changed':node.fields['index']=2
    r=c.query('commit_line_stop',{'preview_token':p['result']['preview_token']})
    if mode in ('changed','native_changed'):assert not r['ok'] and c.lua.globals().dispatches==0;return
    assert r['ok'],r
    stops=c.lua.globals().components[700][3]['stops']
    assert stops[1]['terminal']==1 and stops[2]['terminal']==0
    assert list(stops[1]['stopConfig']['load'].values())==[False,True]
    assert list(stops[1]['stopConfig']['maxLoad'].values())==[.2,.3]
    assert stops[1]['maxAdditionalWaitingTime']==3
