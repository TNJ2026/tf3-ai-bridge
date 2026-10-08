import copy
import json
import math
import hashlib
import pytest
from lupa import LuaRuntime, LuaError
from joint_external import append_external, REBIND, PREVIEW
from build_joint_collection import prepare, code_for, prepared_for_file
from test_city_joint_collection import make_plan, result
from verify_joint_test import acceptance


def approach_plan():
    p=make_plan();h,s,o=prepare(p,'T1');node=s['nodes'][0]['position'];a=math.radians(o['rotation'])
    end=dict(x=o['x']+math.cos(a)*node['x']-math.sin(a)*node['y'],y=o['y']+math.sin(a)*node['x']+math.cos(a)*node['y'])
    start=dict(x=end['x']-100,y=end['y']-100)
    p['roads'].append(dict(id='T1_external',path=[start,dict(x=end['x']-40,y=end['y']-75),end],from_node_hint=999,street_type='country/country_new_medium'))
    return p


def test_joint_external_is_same_guard_before_single_commit():
    p=approach_plan();_,s,o=prepare(p,'T1')
    assert len([r for r in s['roads'] if r.get('buildPhase')=='external'])==2
    ids=[r['entity'] for r in s['roads']+s['nodes']]
    assert len(ids)==len(set(ids)) and max(ids)<0
    preview=code_for(s,o);build=code_for(s,o,True)
    assert 'sendCommand' not in preview and build.count('api.cmd.sendCommand(')==1
    assert PREVIEW in preview and PREVIEW in build
    assert build.index('External vehicle path failed')<build.index('api.cmd.sendCommand(')


def test_pinned_compiled_pack_rejects_changed_plan_or_geometry(tmp_path):
    p=approach_plan();path=tmp_path/'plan.json';path.write_text(json.dumps(p),'utf8');_,s,o=prepare(p,'T1')
    row=dict(spec=s,origin=o,planDigest=hashlib.sha256(path.read_bytes()).hexdigest())
    file=tmp_path/'T1.json';file.write_text(json.dumps(row),'utf8')
    prepared_for_file(path,p,'T1',tmp_path)
    row['spec']['roads'][0]['tangent0']['x']+=1;file.write_text(json.dumps(row),'utf8')
    with pytest.raises(Exception,match='geometry'):prepared_for_file(path,p,'T1',tmp_path)
    path.write_text('{}','utf8')
    with pytest.raises(Exception,match='stale'):prepared_for_file(path,p,'T1',tmp_path)


def test_rebind_never_uses_old_anchor_id_and_rejects_frozen():
    setup='''
    spec={existingBaseNodes={{entity=999,position={x=2,y=3}}},roads={{node0=999,node1=-1}},externalAnchor=999}
    positions={};point=function(p)return p end
    api={type={ComponentType={BASE_NODE=1,CONSTRUCTION=2},Vec2f={new=function(x,y)return{x=x,y=y}end}},engine={}}
    api.engine.util={octree={findEntitiesInCircle=function()return{42}end}}
    api.engine.system={streetSystem={getNodeSegments=function()return{55}end}}
    api.engine.getComponent=function(id,kind)if kind==1 then return{position={x=2,y=3,z=4}}end;return{frozenNodes=FROZEN}end
    api.engine.forEachEntityWithComponent=function(fn)fn(10)end
    '''
    lua=LuaRuntime();lua.execute(setup.replace('FROZEN','{}')+REBIND)
    assert lua.globals().spec.externalAnchor==42
    assert lua.globals().spec.roads[1].node0==42
    with pytest.raises(LuaError,match='Frozen'):LuaRuntime().execute(setup.replace('FROZEN','{42}')+REBIND)


def test_disconnected_external_road_fails_independent_acceptance():
    p=approach_plan();_,s,_=prepare(p,'T1');r=result();r['roads']*=len(s['roads'])
    r['paths']['external']={'inbound':{'verified':True},'outbound':{'verified':False}}
    assert not acceptance(r,True,s)
    assert 'external_road_path' in r['acceptanceFailures']
