"""Typed HQ access preview: directed graph and new-channel read classification."""
import json

import pytest

from test_e2e import SCRIPT
from test_headquarters import hq_game
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments


@pytest.fixture
def access(hq_game):
    lua, call = hq_game
    lua.execute('''
api.type.ComponentType.TRANSPORT_NETWORK=903
components[900]={[api.type.ComponentType.BASE_EDGE]={roadType=api.type.enum.RoadType.STREET}}
local function lane(entity)
 return {edges={{transportModes={[0]=true},forwardOnly=false,
  conns={{entity=entity,index=0},{entity=entity,index=1}}}}}
end
components[900][api.type.ComponentType.TRANSPORT_NETWORK]=lane(900)
PD={errorState={critical=false,messages={},infos={},warnings={}},
 collisionInfo={collisionEntities={}},entity2tn={[-1]=lane(-1)},
 tpNetLinkProposal={toAdd={{link={from={edgeId={entity=-1,index=0},param=0.5},
 to={edgeId={entity=900,index=0},param=0.5}}}}}}
PREVIEW_CALLS=0
api.engine.util.proposal.makeProposalData=function()
 PREVIEW_CALLS=PREVIEW_CALLS+1;return PD
end
''')
    return lua, call


ARGS = dict(town=100, road=900, x=700, y=740, z=2)


def test_typed_directed_graph_single_proposal_no_commit(access):
    from hq_access_probe import analyze
    lua, call = access
    result = call('preview_headquarters_access', **ARGS)
    assert result['previewOnly'] and not result['commitEnabled']
    assert 'preview_token' not in result
    assert analyze(result)['entranceConnected']
    assert lua.globals().PREVIEW_CALLS == 1
    assert lua.globals().SUBMISSIONS is None
    lua.execute('PD.entity2tn[-1].edges[1].forwardOnly=true')
    assert not analyze(call('preview_headquarters_access', **ARGS))['entranceConnected']
    lua.execute('PD.tpNetLinkProposal.toAdd={}')
    assert not analyze(call('preview_headquarters_access', **ARGS))['entranceConnected']


@pytest.mark.parametrize('mutation,message', [
    ('PD.entity2tn[-1].edges[1].forwardOnly=nil', 'direction'),
    ('PD.tpNetLinkProposal.toAdd[1].link.from.param=2', 'automatic link'),
    ('PD.entity2tn[-1].edges[1].conns[1].index=0.5', 'entity/index'),
    ('for i=1,130 do PD.entity2tn[-i]=PD.entity2tn[-1] end', 'network bound'),
])
def test_malformed_graph_stops_without_submission(access, mutation, message):
    lua, call = access
    lua.execute(mutation)
    with pytest.raises(Exception, match=message):
        call('preview_headquarters_access', **ARGS)
    assert lua.globals().SUBMISSIONS is None


def test_collision_does_not_read_graph(access):
    lua, call = access
    lua.execute('PD.collisionInfo.collisionEntities={{entity=42}};PD.entity2tn=nil')
    result = call('preview_headquarters_access', **ARGS)
    assert not result['check']['clear'] and result['check']['collisions'] == [42]
    assert lua.globals().PREVIEW_CALLS == 1
    assert lua.globals().SUBMISSIONS is None


def test_new_channel_preview_is_read_only_across_fresh_module(access, tmp_path):
    lua, _ = access
    lua.execute('''
api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {id=id,name=name,param=param}end
api.cmd.sendCommand=function(cmd)forwarded=cmd end
''')
    gui = lua.execute(SCRIPT.read_text(encoding='utf-8'))
    state = lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    reader = UiLogRequests()
    log = tmp_path/'stdout.txt'
    log.touch()
    output = []
    lua.globals().print = lambda *v: output.append(' '.join(map(str, v)))
    ticket = reader.prepare_build(log, 'preview_headquarters_access', ARGS)
    assert gui['guiHandleEvent'](None, None, None, '', 'tnj_bridge_readonly',
                                 'tnj_bridge_readonly.request', ticket['input']) == 'Submitted; inspect log'
    event = lua.globals().forwarded
    fresh = lua.execute(SCRIPT.read_text(encoding='utf-8'))
    fresh['_internal']['commands']['get_map_info'] = lua.globals().HQ_INTERNAL['commands']['get_map_info']
    fresh['handleEvent'](None, state, '', event['id'], event['name'], event['param'])
    log.write_text('\n'.join(output)+'\n', encoding='utf-8')
    response = reader.read(ticket['id'])['response']
    assert response['ok'], response
    assert response['result']['previewOnly']
    assert lua.globals().PREVIEW_CALLS == 1
    assert lua.globals().SUBMISSIONS is None
    encoded = json.loads(fresh['_internal']['json']['encode'](state['v']))
    assert not encoded.get('uiConstruction', {}).get('pending')


@pytest.mark.parametrize('mode', ['height', '', None, 1, True])
def test_bad_terrain_mode_rejected_before_request(mode):
    with pytest.raises(ValueError):
        validate_build_arguments('get_terrain_grid', dict(x=0, y=0, mode=mode))


@pytest.mark.parametrize('mode', ['surface', 'base'])
def test_supported_terrain_mode(mode):
    validate_build_arguments('get_terrain_grid', dict(x=0, y=0, mode=mode))
