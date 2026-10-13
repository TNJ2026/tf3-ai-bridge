"""Scoped native rail-port proposal tests; mocks do not prove engine connectivity."""
import pytest
from test_ui_consolidated import Channel, NETWORK_FIXTURE
from tf3_mcp.ui_log import validate_build_arguments


def port_channel(tmp_path, rail=True):
    c = Channel(tmp_path, NETWORK_FIXTURE)
    c.lua.globals().NETWORK_RAIL = rail
    p = c.query('preview_network', {'start': {'x':700,'y':700}, 'end': {'x':800,'y':700}, 'template':'town/town_old_small'})
    r = c.query('commit_network', {'preview_token':p['result']['preview_token']})
    assert r['result']['verified'], r
    c.lua.globals().PORT_EDGE = r['result']['edges'][0]
    c.lua.execute('''
      local CT=api.type.ComponentType
      CT.BASE_NODE_CONFIG=107
      api.type.enum.TrafficLightPreference={AUTO=2,YES=0,NO=1}
      local edge=components[PORT_EDGE][CT.BASE_EDGE]
      PORT_NODE=edge.node1
      components[90000]={
       [CT.CONSTRUCTION]={fileName='::/depots/rail/rail_depot.con',
        frozenEdges={PORT_EDGE},frozenNodes={edge.node0},
        transf=api.type.Mat4f.new({}, {}, {}, {x=700,y=700,z=2})},
       [CT.PLAYER_OWNED]={player=api.engine.util.getPlayer()}}
      api.engine.system.streetConnectorSystem.getConstructionEntityForEdge=function(e)
       if e==PORT_EDGE then return 90000 end
      end
      PORT_CONFIG={laneConnections={},crosswalks={},trafficLightPreference=2,
       trafficLightConfig={states={},trafficLightType=-1},doubleSlipSwitch=false,
       userModifiedTrafficLightStates=false}
      components[PORT_NODE][107]=PORT_CONFIG
      local send=api.cmd.sendCommand
      api.cmd.sendCommand=function(cmd,cb)
       if cmd.kind=='build' then LAST_PROPOSAL=cmd.proposal end
       send(cmd,cb)
      end
    ''')
    args = {'start': {'node':c.lua.globals().PORT_NODE}, 'end':{'x':900,'y':700},
            'template':'town/town_old_small', 'reset_empty_rail_ports':True}
    return c, args


@pytest.mark.parametrize('mode', ['ok','changed','lost','retained'])
def test_explicit_rail_port_reset_is_atomic_and_single_use(tmp_path, mode):
    c,args = port_channel(tmp_path)
    assert not c.query('preview_network', {k:v for k,v in args.items() if k!='reset_empty_rail_ports'})['ok']
    p=c.query('preview_network', args)
    assert p['ok'], p
    assert p['result']['resetEmptyRailPorts']==[args['start']['node']]
    token=p['result']['preview_token']
    if mode=='changed': c.lua.execute('PORT_CONFIG.doubleSlipSwitch=true')
    if mode=='lost': c.lua.globals().LOST=True
    if mode=='retained':
        c.lua.execute('''local send=api.cmd.sendCommand
         api.cmd.sendCommand=function(cmd,cb)
          send(cmd,function(...) components[PORT_NODE][107]=PORT_CONFIG;cb(...) end)
         end''')
    before=c.lua.globals().dispatches
    r=c.query('commit_network', {'preview_token':token})
    if mode=='changed':
        assert not r['ok'] and c.lua.globals().dispatches==before
    else:
        assert r['ok'], r
        assert c.lua.globals().dispatches==before+1
        proposal=c.lua.globals().LAST_PROPOSAL['streetProposal']
        assert list(proposal['nodeConfigsToRemove'].values())==[args['start']['node']]
        assert len(proposal['edgesToAdd'])==1
        if mode=='ok':
            assert r['result']['verified'], r
            assert c.lua.globals().components[args['start']['node']][107] is None
            assert not c.state['v']['uiConstruction']['pending']
        else:
            assert not r['result']['verified'] and c.state['v']['uiConstruction']['pending']
            further=c.query('preview_network',args)
            if further['ok'] and further['result'].get('preview_token'):
                assert not c.query('commit_network',{'preview_token':further['result']['preview_token']})['ok']
            assert c.lua.globals().dispatches==before+1
    before=c.lua.globals().dispatches
    assert not c.query('commit_network',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==before


@pytest.mark.parametrize('change', [
    'components[90000][api.type.ComponentType.PLAYER_OWNED].player=999',
    'components[90000][api.type.ComponentType.CONSTRUCTION].fileName="::/depots/tram/tram.con"',
    'components[90000][api.type.ComponentType.CONSTRUCTION].frozenNodes={PORT_NODE}',
    'components[90000][api.type.ComponentType.CONSTRUCTION].frozenEdges={}',
    'api.engine.system.streetConnectorSystem.getConstructionEntityForEdge=function()return nil end',
    'PORT_CONFIG.crosswalks={PORT_EDGE}',
    'PORT_CONFIG.trafficLightConfig.states={1}',
    'PORT_CONFIG.trafficLightConfig.trafficLightType=0',
    'PORT_CONFIG.trafficLightPreference=0',
    'PORT_CONFIG.doubleSlipSwitch=true',
    'PORT_CONFIG.userModifiedTrafficLightStates=true',
    'PORT_CONFIG.userModifiedLaneConnections=true',
    'PORT_CONFIG.doubleSlipSwitch=nil',
])
def test_custom_or_non_port_configs_are_never_reset(tmp_path,change):
    c,args=port_channel(tmp_path)
    c.lua.execute(change)
    before=c.lua.globals().dispatches
    assert not c.query('preview_network',args)['ok']
    assert c.lua.globals().dispatches==before


def test_road_port_config_reset_refused(tmp_path):
    c,args=port_channel(tmp_path,rail=False)
    r=c.query('preview_network',args)
    assert not r['ok'] and 'rail-only' in str(r)
    assert c.lua.globals().dispatches==1


def test_rail_reset_flag_strict_boolean():
    with pytest.raises(ValueError):
        validate_build_arguments('preview_network', {'start':{'node':1},'end':{'x':0,'y':0},
            'template':'rail', 'reset_empty_rail_ports':1})
