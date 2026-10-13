import asyncio
from pathlib import Path
import pytest
from tf3_mcp.frontage_workflow import RoadsidePlacement


def test_absent_native_node_config_is_not_a_parser_error():
    calls=[]
    async def call(cmd,args):
        calls.append(cmd);return {'components':[]}
    workflow=RoadsidePlacement(call,Path('.'),{},lambda:None)
    assert asyncio.run(workflow.component(12,'BASE_NODE_CONFIG')) is None
    assert asyncio.run(workflow.component(12,'BASE_NODE_CONFIG')) is None
    assert len(calls)==1


def test_unknown_split_price_requires_explicit_opt_in_and_remains_unknown():
    preview={'ok':True,'preview_token':'x','structural_only':True,'nativePreviewPassed':False}
    with pytest.raises(ValueError,match='price unavailable'):
        RoadsidePlacement.check_split(preview,False)
    RoadsidePlacement.check_split(preview,True)
    assert 'cost' not in preview
    for flag in ('critical','blocked','placementBlocked','collisions','warnings'):
        with pytest.raises(ValueError):RoadsidePlacement.check_split(dict(preview,**{flag:True}),True)


def test_budget_failure_never_dispatches_even_with_valid_native_token():
    calls=[]
    async def call(cmd,args):
        calls.append(cmd)
        return {'balance':1600000,'speedup':0} if cmd=='get_game_state' else {}
    workflow=RoadsidePlacement(call,Path('.'),{},lambda:None)
    with pytest.raises(ValueError,match='cash floor'):
        asyncio.run(workflow.pay('commit_structure',{'ok':True,'preview_token':'x','cost':200000},5000000,1500000))
    assert calls==['get_game_state','get_validation_state']


def test_unknown_dispatched_outcome_is_never_retried_or_counted_as_success():
    calls=[];record={}
    async def call(cmd,args):
        calls.append(cmd)
        if cmd=='get_game_state':return {'balance':5000000,'speedup':0}
        if cmd=='get_validation_state':return {}
        raise TimeoutError('unknown dispatched outcome')
    workflow=RoadsidePlacement(call,Path('.'),record,lambda:None)
    with pytest.raises(TimeoutError):
        asyncio.run(workflow.pay('commit_structure',{'ok':True,'preview_token':'x','cost':200000},5000000,1500000))
    assert calls.count('commit_structure')==1
    assert 'quotedCommitted' not in record


def test_non_native_preview_cannot_authorize_building_commit():
    async def call(*args):raise AssertionError('No dispatch allowed')
    workflow=RoadsidePlacement(call,Path('.'),{},lambda:None)
    with pytest.raises(ValueError,match='preview rejected'):
        asyncio.run(workflow.pay('commit_structure',{'ok':False,'preview_token':'x','cost':1},100,0))


def test_only_selected_road_collision_can_be_deferred_to_bound_native_preview():
    p=dict(cost=200,ok=False,blocked=True,placementBlocked=True,collisions=[12],
           blocking=dict(streets=[12],townBuildings=[],constructions=[]))
    assert RoadsidePlacement.preflight_fit(p,12,True)
    assert not RoadsidePlacement.preflight_fit(p,12,False)
    assert not RoadsidePlacement.preflight_fit(dict(p,collisions=[12,13]),12,True)
    assert not RoadsidePlacement.preflight_fit(dict(p,critical=True),12,True)
    assert not RoadsidePlacement.preflight_fit(dict(p,unexpected_removals=True),12,True)
    assert not RoadsidePlacement.preflight_fit(dict(p,collisions=[]),12,True)
