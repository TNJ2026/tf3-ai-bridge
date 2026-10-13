"""Passenger module topology across supported sizes; old cargo default retained."""
from lupa import LuaRuntime
import pytest
from test_e2e import SCRIPT, FakeGame
from tf3_mcp.ui_log import validate_build_arguments


@pytest.mark.parametrize('tracks',[1,2,3,4])
@pytest.mark.parametrize('length',[80,120,160,240,320])
@pytest.mark.parametrize('year,era',[(1900,'a'),(1960,'b'),(2000,'c')])
def test_all_passenger_platforms_have_stairs_and_no_cargo(tracks,length,year,era):
    s=SCRIPT.read_text(encoding='utf8')
    helper=s[s.index('local function passengerRailModules'):s.index('commands.build_rail_station =')]
    lua=LuaRuntime(unpack_returned_tuples=True)
    fn=lua.execute('local RAIL_DIR="::/stations/rail/modular_station/";local function railModule(s)return s end\n'+helper+'\nreturn passengerRailModules')
    modules=dict(fn(tracks,length,year))
    assert all('cargo' not in m for m in modules.values())
    platform_slots=[k for k,m in modules.items() if 'platform_passenger_era_' in m]
    stairs=[k for k,m in modules.items() if 'stairs' in m]
    assert len(platform_slots)==(1+tracks//2)*length//40
    assert len([m for m in modules.values() if '/track/simple/' in m])==tracks*length//40
    assert any('main_building_' in m and f'_era_{era}.module' in m for m in modules.values())
    for slot in platform_slots:
        col=(slot-7400000+200)//1000
        assert any((stair-10800000+200)//1000==col for stair in stairs)


def test_passenger_rejects_cargo_specialization_before_proposal(tmp_path):
    with FakeGame(tmp_path/'game') as game:
        call=game.script['_internal']['commands']['build_rail_station']
        with pytest.raises(Exception,match='cannot have cargo specialization'):
            call(game.lua.table_from(dict(x=400,y=400,cargo=False,specialization='bulk')))
        assert game.lua.globals().builds==0
    base=dict(x=0,y=0,rotation=0,tracks=1,length=80,specialization='universal')
    validate_build_arguments('preview_rail_station',base)
    validate_build_arguments('preview_rail_station',dict(base,cargo=False))
    with pytest.raises(ValueError):
        validate_build_arguments('preview_rail_station',dict(base,cargo='false'))
