"""Explicit test-map street-end reset; native regeneration remains live-unverified."""
import pytest
from test_ui_rail_port_reset import port_channel
from tf3_mcp.ui_log import validate_build_arguments


def road_channel(tmp_path):
    c,args=port_channel(tmp_path,rail=False)
    args.pop('reset_empty_rail_ports');args['reset_empty_road_ports']=True
    c.lua.execute('''api.engine.system.streetConnectorSystem.getConstructionEntityForEdge=function()return nil end
    PORT_CONFIG.crosswalks={PORT_EDGE}
    local CT=api.type.ComponentType
    api.type.enum.TransportMode.ELECTRIC_TRAM=6
    ROAD_LANES={{forward=false,transportModes={[0]=true}},{forward=false,transportModes={[2]=true,[4]=true}},
     {forward=true,transportModes={[2]=true,[4]=true}},{forward=true,transportModes={[0]=true}}}
    components[PORT_EDGE][CT.BASE_EDGE].laneConfigs=ROAD_LANES
    local get=api.res.streetTemplateRep.get
    api.res.streetTemplateRep.get=function(id)local t=get(id);t.laneConfigs=ROAD_LANES;return t end
    api.type.BaseNodeLaneConnectionAndEntity={new=function()return {comp={}}end}
    api.type.LaneConnection={new=function()return {}end}
    local send=api.cmd.sendCommand
    api.cmd.sendCommand=function(cmd,cb)
     send(cmd,function(...)
      if cmd.kind=='build' then
       local newId
       for id,cs in pairs(components)do local e=cs[CT.BASE_EDGE]
        if e and id~=PORT_EDGE and (e.node0==PORT_NODE or e.node1==PORT_NODE)then newId=id;e.laneConfigs=ROAD_LANES end
       end
       for _,row in ipairs(cmd.proposal.streetProposal.nodeConfigsToAdd or {})do
        local links={}
        for _,l in ipairs(row.comp.laneConnections)do
         links[#links+1]={segment0=l.segment0<0 and newId or l.segment0,segment1=l.segment1<0 and newId or l.segment1,
          lane0=l.lane0,lane1=WRONG_LANE and 99 or l.lane1,withRoad=l.withRoad,withTram=l.withTram}
        end
        if not MISSING_CONFIG then components[row.entity][107]={laneConnections=links,crosswalks=MISSING_WALK and {} or row.comp.crosswalks}end
       end
      end
      cb(...)
     end)
    end''')
    return c,args


@pytest.mark.parametrize('mode',['ok','changed','lost','missing_config','missing_walk','wrong_lane'])
def test_road_end_reset_one_proposal_and_verified_crosswalk(tmp_path,mode):
    c,args=road_channel(tmp_path)
    default={k:v for k,v in args.items() if k!='reset_empty_road_ports'}
    assert not c.query('preview_network',default)['ok']
    p=c.query('preview_network',args);assert p['ok'],p
    assert p['result']['resetEmptyRoadPorts'][0]['requiredCrosswalks']==[c.lua.globals().PORT_EDGE]
    token=p['result']['preview_token'];before=c.lua.globals().dispatches
    if mode=='changed':c.lua.execute('PORT_CONFIG.crosswalks={999}')
    if mode=='lost':c.lua.globals().LOST=True
    if mode=='missing_config':c.lua.globals().MISSING_CONFIG=True
    if mode=='missing_walk':c.lua.globals().MISSING_WALK=True
    if mode=='wrong_lane':c.lua.globals().WRONG_LANE=True
    r=c.query('commit_network',{'preview_token':token})
    if mode=='changed':
        assert not r['ok'] and c.lua.globals().dispatches==before
    else:
        assert r['ok'],r
        assert c.lua.globals().dispatches==before+1
        assert list(c.lua.globals().LAST_PROPOSAL['streetProposal']['nodeConfigsToRemove'].values())==[args['start']['node']]
        assert len(c.lua.globals().LAST_PROPOSAL['streetProposal']['nodeConfigsToAdd'])==1
        assert r['result']['verified']==(mode=='ok')
        assert bool(c.state['v']['uiConstruction']['pending'])==(mode!='ok')
    before=c.lua.globals().dispatches
    assert not c.query('commit_network',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==before


@pytest.mark.parametrize('change',[
 'api.engine.system.streetConnectorSystem.getConstructionEntityForEdge=function()return 90000 end',
 'components[PORT_EDGE][api.type.ComponentType.BASE_EDGE].type=1',
 'components[PORT_EDGE][api.type.ComponentType.BASE_EDGE].objects={123}',
 'PORT_CONFIG.crosswalks={999}',
 'PORT_CONFIG.crosswalks={PORT_EDGE,PORT_EDGE}',
 'PORT_CONFIG.trafficLightConfig.states={1}',
 'PORT_CONFIG.trafficLightPreference=0',
 'PORT_CONFIG.doubleSlipSwitch=true',
 'PORT_CONFIG.userModifiedTrafficLightStates=true',
 'PORT_CONFIG.userModifiedLaneConnections=true',
])
def test_custom_street_settings_refused(tmp_path,change):
    c,args=road_channel(tmp_path);c.lua.execute(change);before=c.lua.globals().dispatches
    assert not c.query('preview_network',args)['ok']
    assert c.lua.globals().dispatches==before


def test_flag_is_strict_bool():
    with pytest.raises(ValueError):
        validate_build_arguments('preview_network',dict(start={'node':1},end={'x':1,'y':2},template='road',reset_empty_road_ports=1))


def test_rail_and_road_flags_cannot_be_combined(tmp_path):
    c,args=road_channel(tmp_path);args['reset_empty_rail_ports']=True
    assert not c.query('preview_network',args)['ok']


@pytest.mark.parametrize('change',[
 'ROAD_LANES[2].transportModes[5]=true',
 'ROAD_LANES[2].transportModes[4]=false',
 'ROAD_LANES[3].forward=false',
 'ROAD_LANES[5]=ROAD_LANES[3]',
])
def test_non_simple_lane_layout_is_not_guessed(tmp_path,change):
    c,args=road_channel(tmp_path);c.lua.execute(change)
    before=c.lua.globals().dispatches
    assert not c.query('preview_network',args)['ok']
    assert c.lua.globals().dispatches==before
