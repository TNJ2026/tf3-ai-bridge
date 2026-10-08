import copy,sys
from pathlib import Path
import pytest
from lupa.lua52 import LuaRuntime,LuaError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ship_route_checks import compile_checks,prelude,audit_source,select_port

def plan():
    p={'facilities':[dict(id='D',kind='water_depot',position=dict(x=0,y=0))],
       'ports':[dict(id='H',kind='harbor',position=dict(x=1,y=0),service_industries=[1,2])],
       'line_specs':[]}
    for i in (1,2):p['line_specs'].append(dict(id='L'+str(i),mode='SMALL_SHIP',vehicle_model='fishing_boat',
        purchase_base='D',source=dict(existing_industry=i,resource='::/industries/fishing_grounds/fishing_grounds.con',position=dict(x=i+2,y=0)),
        destination='H',source_terminal_index=0,destination_terminal_index=0))
    return p

def test_two_fields_use_three_pairs_six_directions():
    r=compile_checks(plan());assert len(r['pairs'])==3 and r['directionsBeforeNodeDedup']==6
    assert [p['kind']for p in r['pairs']].count('depot_harbor')==1
    assert set(r['pairs'][0]['lines'])=={'L1','L2'}
    assert not r['nativeVerified'] and not r['operationalAccepted']

def test_planned_field_uses_logical_facility_without_fabricating_live_industry():
    p=plan();p['ports'][0]['service_industries']=['NEW_FIELD',2]
    p['facilities'].append(dict(id='NEW_FIELD',kind='industry',
        resource='::/industries/fishing_grounds/fishing_grounds.con',position=dict(x=3,y=0)))
    p['line_specs'][0]['source']='NEW_FIELD'
    before=copy.deepcopy(p);checks=compile_checks(p)
    assert checks==compile_checks(plan())
    assert p==before and 'industries' not in p
    p['facilities'][-1]['resource']='::/industries/oil_well/oil_well.con'
    with pytest.raises(ValueError,match='fishing routes'):compile_checks(p)

def test_duplicate_line_shares_checks_but_different_mode_model_or_terminal_does_not():
    p=plan();p['line_specs'].append(dict(p['line_specs'][0],id='L3'))
    assert len(compile_checks(p)['pairs'])==3
    for key,value in [('mode','SHIP'),('vehicle_model','large_boat'),('destination_terminal_index',1)]:
        q=copy.deepcopy(p);q['line_specs'][2][key]=value
        assert len(compile_checks(q)['pairs'])==5

def test_missing_field_or_depot_or_unknown_port_rejected():
    p=plan();p['line_specs'].pop()
    with pytest.raises(ValueError,match='assignments'):compile_checks(p)
    with pytest.raises(ValueError,match='Unknown port'):compile_checks(plan(),'other')
    p=plan();p['line_specs'][0]['purchase_base']='H'
    with pytest.raises(ValueError,match='shipyard'):compile_checks(p)

def test_explicit_port_id_does_not_bypass_built_pose_validation():
    assert select_port(plan(),{'x':1,'y':0},'H')=='H'
    with pytest.raises(ValueError,match='does not match'):
        select_port(plan(),{'x':100,'y':0},'H')
    with pytest.raises(ValueError,match='does not match'):
        select_port(plan(),{'x':1,'y':0},'other')

SETUP='''
calls=0
api={type={ComponentType={TRANSPORT_NETWORK=1},enum={TransportMode={SMALL_SHIP=1,SHIP=2}}},engine={
getComponent=function(id,ct)if id==999 then return nil end;return{nodes={{},{}}}end,
util={pathfinding={findPathNodeToNode=function(a,b,m)calls=calls+1;if a[1].entity==2 then return{}end;return{{}}end}}}}
local function n(id,i)return{entity=id,index=i or 0}end
a={n(1)};b={n(2)}
'''

def run(code):
    lua=LuaRuntime(unpack_returned_tuples=True);lua.execute(SETUP)
    r=lua.execute(prelude()+code);return lua,r

def test_directional_cache_keeps_empty_return_path_and_does_not_query_pairs_twice():
    lua,r=run('''local q,s=newShipRouteChecker()
local f=q(a,b,1,'boat');local r=q(b,a,1,'boat');q(a,b,1,'boat');q(b,a,1,'boat')
return {forward=f.reachable,back=r.reachable,queries=s.queries,hits=s.hits}''')
    assert r['forward'] and not r['back'] and r['queries']==2 and r['hits']==2
    assert lua.globals().calls==2

def test_cache_separates_modes_profiles_nodes_and_new_batches():
    lua,_=run('''local q=newShipRouteChecker();q(a,b,1,'boat');q(a,b,2,'boat');q(a,b,1,'other')
q({{entity=1,index=1}},b,1,'boat');local fresh=newShipRouteChecker();fresh(a,b,1,'boat')''')
    assert lua.globals().calls==5

@pytest.mark.parametrize('nodes',['{}','{{entity=999,index=0}}','{{entity=1,index=9}}','{{entity=-1,index=0}}'])
def test_invalid_endpoint_never_enters_native_query(nodes):
    lua=LuaRuntime();lua.execute(SETUP)
    with pytest.raises(LuaError):lua.execute(prelude()+"local q=newShipRouteChecker();q("+nodes+",b,1,'boat')")
    assert lua.globals().calls==0

def test_full_audit_resolves_current_nodes_and_uses_six_queries():
    lua=LuaRuntime(unpack_returned_tuples=True)
    checks=compile_checks(plan())
    def table(v):
        if isinstance(v,dict):return lua.table_from({k:table(x)for k,x in v.items()})
        if isinstance(v,list):return lua.table_from([table(x)for x in v])
        return v
    lua.globals().checks=table(checks)
    lua.execute('''
calls=0;local CT={CONSTRUCTION=1,STATION=2,VEHICLE_DEPOT=3,TRANSPORT_NETWORK=4}
local function c(x,res,station,depot)return{fileName=res,transf={cols=function()return{x=x,y=0}end},stations=station and{station}or{},depots=depot and{depot}or{}}end
local cs={[10]=c(0,'::/depots/water/water_depot.con',nil,50),[11]=c(1,'::/stations/water/harbor_modular.con',51),[12]=c(3,'::/industries/fishing_grounds/fishing_grounds.con',52),[13]=c(4,'::/industries/fishing_grounds/fishing_grounds.con',53)}
api={type={ComponentType=CT,enum={TransportMode={SMALL_SHIP=1,SHIP=2}}},engine={
forEachEntityWithComponent=function(fn)for id in pairs(cs)do fn(id)end end,
getComponent=function(id,ct)
 if ct==1 then return cs[id]elseif ct==4 then return{nodes={{},{}}}
 elseif ct==3 then return{transportModes={[1]=true},outNodes={{entity=50,index=0}},inNodes={{entity=50,index=1}}}
 else return{terminals={{transportModes={[1]=true},vehicleNodeId={entity=id,index=0}}}}end
end,util={pathfinding={findPathNodeToNode=function()calls=calls+1;return{{}}end}}}}
B={json={decode=function()return checks end,encode=function(x)return x end}}
''')
    r=lua.execute(audit_source(checks))
    assert r['verified'] and len(r['pairs'])==3 and lua.globals().calls==6
    assert not r['modelRestrictionsVerified'] and not r['operationalAccepted']
