import pytest
from planning_shared_hubs import shared_fishing_port, validate_fishing_assignments, finalize_land_quantities


def field(i,x):
    return dict(id=i,position=dict(x=x,y=0),resource='industry/fishing_grounds/fish.con')


def port():
    return dict(id='P1',industry=1,service_industries=[1],position=dict(x=0,y=0),annual_forecast=10)


def direct(a,b):return [a,b]


@pytest.mark.parametrize('x,expected',[(2999,True),(3000,True),(3000.01,False)])
def test_pair_distance_inclusive(x,expected):
    rows={1:field(1,0),2:field(2,x)}
    assert bool(shared_fishing_port(rows[2],[port()],rows,direct,10)) is expected


def test_no_transitive_pair_and_capacity_and_water():
    rows={i:field(i,(i-1)*1500) for i in (1,2,3)}
    p=port()
    assert shared_fishing_port(rows[2],[p],rows,direct,10,20)
    assert not shared_fishing_port(rows[2],[p],rows,direct,10,19)
    assert not shared_fishing_port(rows[2],[p],rows,lambda a,b:[],10)
    assert not shared_fishing_port(rows[2],[p],rows,lambda a,b:[a,dict(x=0,y=9000),b],10)
    p['service_industries']=[1,2]
    assert not shared_fishing_port(rows[3],[p],rows,direct,10)
    with pytest.raises(ValueError):shared_fishing_port(rows[3],[p],rows,direct,10,0)


def test_fishing_assignment_integrity():
    rows={1:field(1,0),2:field(2,3000),3:field(3,5000)}
    p=port();p['service_industries']=[1,2]
    assert set(validate_fishing_assignments([p],rows))=={1,2}
    with pytest.raises(ValueError):validate_fishing_assignments([p,port()],rows)
    p['service_industries']=[1,3]
    with pytest.raises(ValueError):validate_fishing_assignments([p],rows)
    p['service_industries']=[2]
    with pytest.raises(ValueError):validate_fishing_assignments([p],rows)
    p['service_industries']=[1];rows[1]['resource']='oil_platform'
    with pytest.raises(ValueError):validate_fishing_assignments([p],rows)


def test_land_count_tracks_transfer_not_object_count():
    hubs={f'T{i}':dict(owner=f'T{i}',entity=i,kind='city',facilities=dict(heliport=f'F{i}'),existing=i==3)for i in (1,2,3)}
    facilities=[dict(id=f'F{i}')for i in (1,2,3)]
    roads=[dict(id='r1',to_facility='F1'),dict(id='r2',depends_on=['F2'])]
    routes=[dict(id='r',source=1,destination=2,annual=10,cargo=6,transfer_chain=[dict(mode='TRUCK',**{'from':{'industry':1},'to':{'town':2}})])]
    args=(hubs,facilities,roads,routes,[dict(id=i)for i in (1,2,3)],[])
    kept,fs,rs,report=finalize_land_quantities(*args)
    assert set(kept)=={'T3'} and fs==[dict(id='F3')] and not rs
    assert len(report['service_inventory'])==3 and report['new_land_collections']==0
    routes[0]['transfer_chain'].append(dict(mode='HELICOPTER',source_second='F1',maintenance_base='F2'))
    kept,fs,rs,report=finalize_land_quantities(*args)
    assert set(kept)==set(hubs) and report['new_land_collections']==2
    assert report['decisions'][0]['traffic'][0]['annual']==10


def test_neighbor_city_review_and_offline_construction_gate(tmp_path):
    import json,subprocess,sys
    from pathlib import Path
    from planning_shared_hubs import city_siting_reviews
    cities=[dict(id=1,position=dict(x=2700,y=-2768)),dict(id=2,position=dict(x=2480,y=580))]
    hubs=[dict(owner='T1',entity=1,kind='city',position=dict(x=2053,y=-1972)),dict(owner='T2',entity=2,kind='city',position=dict(x=2219,y=-1439))]
    reviews=city_siting_reviews(hubs,cities)
    assert len(reviews)==1 and 550<reviews[0]['anchor_distance_m']<570
    assert reviews[0]['status']=='pending_comparison' and len(reviews[0]['alternatives'])==3
    assert reviews[0]['service'][0]['round_trip_seconds'] is None
    root=Path(__file__).resolve().parents[2]
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(dict(hubs=hubs,cities=cities)),encoding='utf8')
    result=subprocess.run([sys.executable,str(root/'scripts/construct_planned_map.py'),'--plan',str(plan),'--output',str(tmp_path/'out'),'--owners','T1','--authorize-build'],capture_output=True,text=True)
    assert result.returncode==2 and 'City siting comparison required' in result.stderr
    assert not (tmp_path/'out/ledger.json').exists()


def test_distant_local_city_collections_need_no_proximity_review():
    from planning_shared_hubs import city_siting_reviews
    cities=[dict(id=i,position=dict(x=i*5000,y=0))for i in (1,2)]
    hubs=[dict(owner=f'T{i}',entity=i,kind='city',position=dict(x=i*5000,y=700))for i in (1,2)]
    assert city_siting_reviews(hubs,cities)==[]
