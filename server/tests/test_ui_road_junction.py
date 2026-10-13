"""Atomic, opt-in road branching; mocks do not establish native safety."""
import pytest
from test_ui_consolidated import Channel, NETWORK_FIXTURE
from tf3_mcp.ui_log import validate_build_arguments


def junction_channel(tmp_path, reverse=False):
    c=Channel(tmp_path,NETWORK_FIXTURE)
    args=dict(start={'x':700,'y':700},via=[{'x':800,'y':700}],end={'x':900,'y':700},template='town/town_old_small')
    p=c.query('preview_network',args)
    built=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert built['result']['verified'],built
    c.lua.execute('''
      local CT=api.type.ComponentType;CT.BASE_NODE_CONFIG=107
      api.type.enum.TrafficLightPreference={AUTO=2}
      api.type.enum.TransportMode.ELECTRIC_TRAM=6
      api.type.BaseNodeLaneConnectionAndEntity={new=function()return {comp={}}end}
      api.type.LaneConnection={new=function()return {}end}
      LANES={{forward=false,transportModes={[0]=true}},
       {forward=false,transportModes={[2]=true,[4]=true}},
       {forward=true,transportModes={[2]=true,[4]=true}},
       {forward=true,transportModes={[0]=true}}}
      local get=api.res.streetTemplateRep.get
      api.res.streetTemplateRep.get=function(id)local t=get(id);t.laneConfigs=LANES;return t end
      for id,cs in pairs(components)do
       local n=cs[CT.BASE_NODE];if n and n.position.x==800 and n.position.y==700 then JNODE=id end
      end
      OLD=api.engine.system.streetSystem.getNodeSegments(JNODE);table.sort(OLD)
      for _,id in ipairs(OLD)do components[id][CT.BASE_EDGE].laneConfigs=LANES end
      CONFIG={laneConnections={{segment0=OLD[1],segment1=OLD[2],lane0=1,lane1=2,withRoad=true,withTram=false},
       {segment0=OLD[2],segment1=OLD[1],lane0=1,lane1=2,withRoad=true,withTram=false}},
       crosswalks={OLD[1]},trafficLightPreference=2,trafficLightConfig={states={},trafficLightType=-1},
       doubleSlipSwitch=false,userModifiedTrafficLightStates=false}
      components[JNODE][107]=CONFIG
      local send=api.cmd.sendCommand
      api.cmd.sendCommand=function(cmd,cb)
       LAST_PROPOSAL=cmd.proposal
       local before={};for id in pairs(components)do before[id]=true end
       send(cmd,function(...)
        local fresh
        for id,cs in pairs(components)do if not before[id] and cs[CT.BASE_EDGE]then fresh=id;cs[CT.BASE_EDGE].laneConfigs=LANES end end
        for _,v in ipairs(cmd.proposal.streetProposal.nodeConfigsToAdd or {})do
         local cfg=v.comp;local turns={}
         for _,l in ipairs(cfg.laneConnections)do
          turns[#turns+1]={segment0=l.segment0<0 and fresh or l.segment0,segment1=l.segment1<0 and fresh or l.segment1,
           lane0=l.lane0,lane1=WRONG_LANE and 99 or l.lane1,withRoad=l.withRoad,withTram=l.withTram}
         end
         components[v.entity][107]={laneConnections=turns,crosswalks=MISSING_WALK and {} or cfg.crosswalks,
          trafficLightPreference=cfg.trafficLightPreference,trafficLightConfig=cfg.trafficLightConfig,
          doubleSlipSwitch=cfg.doubleSlipSwitch,userModifiedTrafficLightStates=cfg.userModifiedTrafficLightStates}
         if AUTO_PHASES then
          components[v.entity][107].trafficLightConfig={trafficLightType=-1,states=AUTO_PHASES}
         end
         if READBACK_SIGNAL_CHANGE then READBACK_SIGNAL_CHANGE(components[v.entity][107])end
        end
        if CHANGED_OLD then components[OLD[1]][CT.BASE_EDGE].tangent0.x=999 end
        if MISSING_NETWORK then components[JNODE][998]=nil end
        cb(...)
       end)
      end
    ''')
    args=dict(start={'node':c.lua.globals().JNODE},end={'x':800,'y':800},template='town/town_old_small',connect_road_junctions=True)
    if reverse:args['start'],args['end']=args['end'],args['start']
    return c,args


@pytest.mark.parametrize('reverse',[False,True])
def test_branch_preserves_controls_and_commits_once(tmp_path,reverse):
    c,args=junction_channel(tmp_path,reverse)
    before=c.lua.globals().dispatches
    assert not c.query('preview_network',{k:v for k,v in args.items() if k!='connect_road_junctions'})['ok']
    p=c.query('preview_network',args);assert p['ok'],p
    assert c.lua.globals().dispatches==before
    assert len(c.lua.globals().CONFIG['laneConnections'])==2
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['ok'] and r['result']['verified'],r
    assert r['result']['junctions'][0]['configurationVerified']
    assert not r['result']['serviceConnectivityVerified']
    assert not r['result']['junctions'][0]['directedPathsVerified']
    assert c.lua.globals().dispatches==before+1
    sp=c.lua.globals().LAST_PROPOSAL['streetProposal']
    assert len(sp['nodeConfigsToRemove'])==1 and len(sp['nodeConfigsToAdd'])==1
    assert len(sp['nodeConfigsToAdd'][1]['comp']['laneConnections'])==6
    assert len(c.lua.globals().CONFIG['laneConnections'])==2  # no live alias mutation
    assert not c.query('commit_network',{'preview_token':p['result']['preview_token']})['ok']
    assert c.lua.globals().dispatches==before+1


@pytest.mark.parametrize('change',[
    'CONFIG.userModifiedTrafficLightStates=true',
    'CONFIG.trafficLightConfig.states={1}',
    'CONFIG.userModifiedLaneConnections=true',
    'CONFIG.crosswalks={99999}',
    'CONFIG.crosswalks={OLD[1],OLD[1]}',
    'CONFIG.laneConnections[1].lane0=2',
    'CONFIG.laneConnections[2]=nil',
    'LANES[2].transportModes[4]=false',
    'LANES[2].transportModes[5]=true',
    'components[OLD[1]][api.type.ComponentType.BASE_EDGE].objects={1}',
    'components[OLD[1]][api.type.ComponentType.BASE_EDGE].type=1',
    'components[OLD[1]][998]=nil',
    'api.engine.system.streetConnectorSystem.getConstructionEntityForEdge=function()return 123 end',
])
def test_unsupported_junction_never_previews_or_dispatches(tmp_path,change):
    c,args=junction_channel(tmp_path);c.lua.execute(change)
    before=c.lua.globals().dispatches
    r=c.query('preview_network',args)
    assert not r['ok'],r
    assert c.lua.globals().dispatches==before


@pytest.mark.parametrize('change',[
    'CONFIG.crosswalks={}',
    'components[OLD[1]][api.type.ComponentType.BASE_EDGE].tangent0.x=91',
    'components[JNODE][api.type.ComponentType.BASE_NODE].position.x=801',
])
def test_changed_preview_is_consumed_without_dispatch(tmp_path,change):
    c,args=junction_channel(tmp_path)
    p=c.query('preview_network',args);assert p['ok'],p
    before=c.lua.globals().dispatches;c.lua.execute(change)
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert not r['ok'] and c.lua.globals().dispatches==before,r
    assert not c.query('commit_network',{'preview_token':p['result']['preview_token']})['ok']
    assert c.lua.globals().dispatches==before


@pytest.mark.parametrize('flag',['WRONG_LANE','MISSING_WALK','CHANGED_OLD','MISSING_NETWORK'])
def test_wrong_native_readback_retains_pending(tmp_path,flag):
    c,args=junction_channel(tmp_path)
    p=c.query('preview_network',args);assert p['ok'],p
    before=c.lua.globals().dispatches;c.lua.globals()[flag]=True
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['ok'] and r['result']['built'] and not r['result']['verified'],r
    assert c.state['v']['uiConstruction']['pending']
    assert c.lua.globals().dispatches==before+1


def test_junction_flag_strict_bool():
    with pytest.raises(ValueError):
        validate_build_arguments('preview_network',dict(start={'node':1},end={'x':0,'y':50},template='x',connect_road_junctions=1))


def test_medium_branch_expands_directional_turns(tmp_path):
    c,args=junction_channel(tmp_path)
    c.lua.execute('''LANES={LANES[1],LANES[2],LANES[2],LANES[3],LANES[3],LANES[4]}''')
    p=c.query('preview_network',args);assert p['ok'],p
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['ok'] and r['result']['verified'],r
    assert len(c.lua.globals().LAST_PROPOSAL['streetProposal']['nodeConfigsToAdd'][1]['comp']['laneConnections'])==10


def test_native_node_wrappers_do_not_alias_or_change_identity(tmp_path):
    from test_ui_network_native_snapshots import NativeRecord
    c,args=junction_channel(tmp_path)
    cfg=c.lua.globals().CONFIG
    fields={k:v for k,v in cfg.items()}
    fields['trafficLightConfig']=NativeRecord(states=cfg['trafficLightConfig']['states'],trafficLightType=-1)
    c.lua.globals().native_config=lambda:NativeRecord(**fields)
    c.lua.execute('''local get=api.engine.getComponent
     api.engine.getComponent=function(id,ct)
      if id==JNODE and ct==107 and components[JNODE][107]==CONFIG then return native_config()end
      return get(id,ct)
     end''')
    p=c.query('preview_network',args);assert p['ok'],p
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['ok'] and r['result']['verified'],r
    assert len(cfg['laneConnections'])==2


def test_branch_cannot_expand_an_existing_three_way_junction(tmp_path):
    c,args=junction_channel(tmp_path)
    p=c.query('preview_network',args)
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['result']['verified']
    before=c.lua.globals().dispatches
    args['end']={'x':800,'y':600}
    p=c.query('preview_network',args)
    assert not p['ok'] and 'degree-two' in p['error'],p
    assert c.lua.globals().dispatches==before


def test_native_auto_signal_phases_are_regenerated_after_branch(tmp_path):
    c,args=junction_channel(tmp_path)
    c.lua.execute('''AUTO_PHASES={
      {lockedLanes={2,3,4,5},duration=18.855201721191,minDuration=1.5,canSkip=true},
      {lockedLanes={0,1,2,3,4,5},duration=6,minDuration=1.5,canSkip=true},
      {lockedLanes={0,1},duration=18.855201721191,minDuration=1.5,canSkip=true}}
    ''')
    p=c.query('preview_network',args)
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['ok'] and r['result']['verified'],r
    assert not c.state['v']['uiConstruction']['pending']
    assert len(c.lua.globals().CONFIG['trafficLightConfig']['states'])==0


@pytest.mark.parametrize('change',[
    'cfg.trafficLightPreference=0',
    'cfg.userModifiedTrafficLightStates=true',
    'cfg.userModifiedLaneConnections=true',
    'cfg.doubleSlipSwitch=true',
    'cfg.trafficLightConfig.trafficLightType=1',
    'cfg.trafficLightConfig.states[1].lockedLanes={6}',
    'cfg.trafficLightConfig.states[1].lockedLanes={-1}',
    'cfg.trafficLightConfig.states[1].lockedLanes={1,1}',
    'cfg.trafficLightConfig.states[1].lockedLanes={0.5}',
    'cfg.trafficLightConfig.states[1].duration=0/0',
    'cfg.trafficLightConfig.states[1].duration=math.huge',
    'cfg.trafficLightConfig.states[1].duration=1',
    'cfg.trafficLightConfig.states[1].minDuration=-1',
    'cfg.trafficLightConfig.states[1].canSkip=1',
])
def test_changed_signal_policy_or_invalid_generated_phase_stays_pending(tmp_path,change):
    c,args=junction_channel(tmp_path)
    c.lua.execute('''AUTO_PHASES={{lockedLanes={0,1},duration=18.855201721191,minDuration=1.5,canSkip=true}}
      READBACK_SIGNAL_CHANGE=function(cfg) '''+change+''' end''')
    p=c.query('preview_network',args)
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['ok'] and r['result']['built'] and not r['result']['verified'],r
    assert c.state['v']['uiConstruction']['pending']
