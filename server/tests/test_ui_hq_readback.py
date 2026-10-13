"""Existing HQ graph audit without proposals, full CONSTRUCTION or native paths."""
import json

import pytest

from test_ui_hq_access import access
from test_headquarters import hq_game
from hq_access_probe import analyze
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments
from test_e2e import SCRIPT


@pytest.fixture
def existing(access):
    lua, call = access
    lua.execute('''
local CT=api.type.ComponentType
CT.TP_NET_LINK=904;CT.BASE_EDGE_STREET=905
components[700]={[CT.CONSTRUCTION]={fileName="::/landmarks/hq/headquarter.con",
 transf={1,0,0,0,0,1,0,0,0,0,1,0,700,740,2,1},subconstructions={701},
 persistentMetadata=string.rep("x",100000)}}
components[701]={[CT.TRANSPORT_NETWORK]={edges={{transportModes={[0]=true},forwardOnly=false,
 conns={{entity=701,index=0},{entity=701,index=1}}}}}}
components[900][CT.BASE_EDGE].node0=901;components[900][CT.BASE_EDGE].node1=902
components[900][CT.BASE_EDGE_STREET]={}
components[901]={[CT.BASE_NODE]={position={x=0,y=0,z=0}}}
components[902]={[CT.BASE_NODE]={position={x=20,y=0,z=0}}}
components[703]={[CT.TP_NET_LINK]={from={edgeId={entity=701,index=0},param=0.5},
 to={edgeId={entity=900,index=0},param=0.25}}}
api.engine.system.streetConnectorSystem.getConstructionEntityForSubconstruction=function(id)
 if id==701 or id==702 then return 700 end
end
api.engine.system.tpNetLinkSystem={getEdgeId2linkEntities=function()return {{703},{703}} end}
''')
    return lua, call


def test_existing_graph_and_disconnected_subconstruction(existing):
    lua, call = existing
    result = call('get_facility_access', entity=700, person_graph=True)
    graph = result['personGraph']
    assert graph['nativeProposalCalls'] == 0 and not graph['commitEnabled']
    assert graph['links'][0]['from']['param'] == .5
    assert graph['links'][0]['to']['param'] == .25
    assert analyze(graph, existing_entities=graph['hqEntities'])['entranceConnected']
    assert len(json.dumps(result)) < 6000
    assert 'persistentMetadata' not in json.dumps(result)
    assert lua.globals().PREVIEW_CALLS == 0 and lua.globals().SUBMISSIONS is None
    # An unlinked PERSON subnetwork must participate, not silently disappear.
    lua.execute('''
local CT=api.type.ComponentType
components[700][CT.CONSTRUCTION].subconstructions={701,702}
components[702]={[CT.TRANSPORT_NETWORK]={edges={{transportModes={[0]=true},forwardOnly=false,
 conns={{entity=702,index=0},{entity=702,index=1}}}}}}
''')
    graph = call('get_facility_access', entity=700, person_graph=True)['personGraph']
    assert not analyze(graph, existing_entities=graph['hqEntities'])['entranceConnected']


def test_existing_graph_oneway_not_mistaken_for_both_directions(existing):
    lua, call = existing
    lua.execute('components[701][api.type.ComponentType.TRANSPORT_NETWORK].edges[1].forwardOnly=true')
    graph = call('get_facility_access', entity=700, person_graph=True)['personGraph']
    assert not analyze(graph, existing_entities=graph['hqEntities'])['entranceConnected']


@pytest.mark.parametrize('mutation,message', [
    ('components[700][api.type.ComponentType.CONSTRUCTION].subconstructions=nil', 'inventory'),
    ('components[700][api.type.ComponentType.CONSTRUCTION].subconstructions={}', 'outside inspected'),
    ('components[701]=nil', 'removed'),
    ('components[703][api.type.ComponentType.TP_NET_LINK].from.param=2', 'automatic link'),
    ('components[701][api.type.ComponentType.TRANSPORT_NETWORK].edges[1].forwardOnly=nil', 'direction'),
    ('local n=components[701][api.type.ComponentType.TRANSPORT_NETWORK];for i=2,257 do n.edges[i]=n.edges[1] end', 'edge bound'),
])
def test_unknown_graph_fails_closed(existing, mutation, message):
    lua, call = existing
    lua.execute(mutation)
    with pytest.raises(Exception, match=message):
        call('get_facility_access', entity=700, person_graph=True)
    assert lua.globals().PREVIEW_CALLS == 0 and lua.globals().SUBMISSIONS is None


def test_opt_in_schema_and_legacy_response(existing):
    _, call = existing
    for args in ({'entity':700}, {'entity':700,'person_graph':True}, {'entity':700,'person_graph':False}):
        validate_build_arguments('get_facility_access',args)
    with pytest.raises(ValueError):
        validate_build_arguments('get_facility_access',{'entity':700,'person_graph':1})
    assert 'personGraph' not in call('get_facility_access',entity=700)


def test_new_channel_readback_no_durable_mutation(existing, tmp_path):
    lua, _ = existing
    lua.execute('''
api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {id=id,name=name,param=param}end
api.cmd.sendCommand=function(cmd)forwarded=cmd end
''')
    gui = lua.execute(SCRIPT.read_text(encoding='utf8'))
    state = lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    log = tmp_path/'stdout.txt'
    log.touch()
    reader = UiLogRequests()
    output = []
    lua.globals().print = lambda *v: output.append(' '.join(map(str,v)))
    ticket = reader.prepare_build(log,'get_facility_access',{'entity':700,'person_graph':True})
    assert gui['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly',
                                 'tnj_bridge_readonly.request',ticket['input']) == 'Submitted; inspect log'
    event = lua.globals().forwarded
    fresh = lua.execute(SCRIPT.read_text(encoding='utf8'))
    fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
    log.write_text('\n'.join(output)+'\n',encoding='utf8')
    response = reader.read(ticket['id'])['response']
    assert response['ok'],response
    graph = response['result']['personGraph']
    assert analyze(graph,existing_entities=graph['hqEntities'])['entranceConnected']
    encoded = json.loads(fresh['_internal']['json']['encode'](state['v']))
    assert not encoded.get('uiConstruction',{}).get('pending')
    assert not encoded.get('uiConstruction',{}).get('order')
    assert lua.globals().PREVIEW_CALLS == 0 and lua.globals().SUBMISSIONS is None


@pytest.mark.parametrize("junction", [901, 902])
def test_linked_frontage_junction_inventory(existing, junction):
    lua, call = existing
    lua.execute(f"""
local CT=api.type.ComponentType
components[{junction}][CT.TRANSPORT_NETWORK]={{edges={{{{transportModes={{[0]=true}},forwardOnly=false,
 conns={{{{entity={junction},index=0}},{{entity={junction},index=1}}}}}}}}}}
components[704]={{[CT.TP_NET_LINK]={{from={{edgeId={{entity=701,index=0}},param=0.5}},
 to={{edgeId={{entity={junction},index=0}},param=0.25}}}}}}
api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities=function()return {{{{703,704,704}}}} end
""")
    r=call('get_facility_access',entity=700,person_graph=True)
    assert r['personGraph']['junctions']==[junction]
    assert len(r['personGraph']['links'])==2
    assert len([n for n in r['personGraph']['networks'] if n['entity']==junction])==1
    assert lua.globals().PREVIEW_CALLS==0 and lua.globals().SUBMISSIONS is None
    lua.execute(f'components[{junction}][api.type.ComponentType.TRANSPORT_NETWORK]=nil')
    with pytest.raises(Exception,match='Missing linked'):
        call('get_facility_access',entity=700,person_graph=True)


def test_unrelated_junction_is_not_whitelisted(existing):
    lua,call=existing
    lua.execute("""
local CT=api.type.ComponentType
components[999]={[CT.BASE_NODE]={position={x=0,y=0,z=0}}}
components[704]={[CT.TP_NET_LINK]={from={edgeId={entity=701,index=0},param=0.5},
 to={edgeId={entity=999,index=0},param=0.25}}}
api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities=function()return {{703,704}} end
""")
    with pytest.raises(Exception,match='outside inspected inventory'):
        call('get_facility_access',entity=700,person_graph=True)


@pytest.mark.parametrize('extra,passed',[(300,True),(1025,False)])
def test_person_output_and_native_scan_have_separate_bounds(existing,extra,passed):
    lua,call=existing
    lua.execute(f"""
local e=components[900][api.type.ComponentType.TRANSPORT_NETWORK].edges
for i=1,{extra} do e[#e+1]={{transportModes={{[2]=true}},forwardOnly=false,
 conns={{{{entity=901,index=0}},{{entity=902,index=0}}}}}} end
""")
    if not passed:
        with pytest.raises(Exception,match='native scan bound'):
            call('get_facility_access',entity=700,person_graph=True)
    else:
        r=call('get_facility_access',entity=700,person_graph=True)['personGraph']
        assert r['scannedNativeEdges']>300 and r['personEdgeCount']<10
        assert sum(len(n['edges']) for n in r['networks'])==r['personEdgeCount']
    assert lua.globals().PREVIEW_CALLS==0 and lua.globals().SUBMISSIONS is None
