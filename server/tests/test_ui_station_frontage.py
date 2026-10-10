"""Street stations opt into the existing bounded joint frontage proposal."""
import pytest
from lupa import LuaError
from test_ui_frontage import frontage, SOURCE
from tf3_mcp.ui_log import validate_build_arguments


@pytest.fixture
def station_placement(frontage):
    lua, adapter = frontage
    lua.globals().frontageAdapter = adapter
    lua.execute('''
TERMINAL_CON="::/stations/street/modular_street_station/modular_terminal.con"
DEPOT_FILES={ROAD="road_depot",TRAM="tram_depot"};ENTRANCE_OFFSET={}
function terrainHeight()return 1 end
function resolveFacing()return 0 end
function transfAt(x,y,z,r)return {x=x,y=y,z=z,r=r}end
function roundPos(p)return p end
function round1(v)return v end
api.type.SimpleProposal={new=function()return {streetProposal={}}end,
 ConstructionEntity={new=function()return {}end}}
local original=previewProposal
function previewProposal(p)observedProposal=p;return original(p)end
''')
    source = SOURCE.read_text(encoding='utf-8')
    body = source[source.index('local function placeConstruction('):source.index('-- Generic facility support.')]
    place = lua.execute(body + '\nreturn placeConstruction')
    return lua, place


@pytest.mark.parametrize('cargo', [True, False])
@pytest.mark.parametrize('explicit_height', [False, True])
def test_station_frontage_reuses_joint_builder_and_preserves_modules(station_placement, cargo, explicit_height):
    lua, place = station_placement
    args = {'x': 0, 'y': 30, 'preview': True, 'frontage_node': 10}
    if explicit_height:
        lua.execute('function terrainHeight()return 1.7 end')
        args['z'] = 1
    params = lua.table_from({'seed': 1, 'modules': lua.table_from({20115503: lua.table_from({'name': 'entrance_exit', 'variant': 0})})})
    out = place(lua.table_from(args),
                lua.globals().TERMINAL_CON, lambda: params, lua.table_from({'kind': 'cargo' if cargo else 'passenger'}))
    assert out['ok'] and out['frontage']['nativeEntranceNode'] == -8
    assert not out['frontage']['connectionsVerified']
    p = lua.globals().observedProposal
    assert p['constructionsToAdd'][1]['transf']['z'] == 1
    assert out['foundationHeightAdjustment'] == pytest.approx(-.7 if explicit_height else 0)
    assert p['constructionsToAdd'][1]['params']['modules'][20115503]['name'] == 'entrance_exit'
    assert set(p['streetProposal']['edgesToRemove'].values()) == {21, 22}
    assert p['streetProposal']['edgesToAdd'][1]['comp']['node1'] == -8
    assert p['streetProposal']['edgesToAdd'][2]['comp']['node0'] == -8
    assert set(v['entity'] for v in p['streetProposal']['nodeConfigsToAdd'].values()) == {11, 12}
    with pytest.raises(LuaError, match='Direct frontage supports'):
        place(lua.table_from({'x': 0, 'y': 30, 'preview': True, 'frontage_node': 10}),
              'unsupported_airport', lambda: params, lua.table())


@pytest.mark.parametrize('cargo', [True, False])
def test_station_frontage_is_optional_and_validated(cargo):
    args = dict(x=1, y=2, rotation=90, cargo=cargo, size=1)
    validate_build_arguments('preview_station', args)
    validate_build_arguments('preview_station', dict(args, frontage_node=10))
    for bad in (-1, True, 1.2, '10'):
        with pytest.raises(ValueError):
            validate_build_arguments('preview_station', dict(args, frontage_node=bad))


@pytest.mark.parametrize('change', [dict(z=3.01), dict(z=-1.01), dict(z=float('nan')),
                                   dict(z=float('inf')), dict(z=True), dict(z='1'),
                                   dict(z=1, frontage_node=None)])
def test_explicit_height_rejected_before_native_preview(station_placement, change):
    lua, place = station_placement
    args = dict(x=0, y=30, preview=True, frontage_node=10, **{'z': 1})
    args.update(change)
    with pytest.raises(LuaError):
        place(lua.table_from(args), lua.globals().TERMINAL_CON, lambda: lua.table(), lua.table())
    assert lua.globals().previews == 0


def test_explicit_height_does_not_bypass_native_height_guard(station_placement):
    lua, place = station_placement
    lua.execute('height=2')
    with pytest.raises(LuaError, match='Native entrance height differs'):
        place(lua.table_from(dict(x=0, y=30, z=1, preview=True, frontage_node=10)),
              lua.globals().TERMINAL_CON, lambda: lua.table(), lua.table())


@pytest.mark.parametrize('command,extra', [('preview_station', dict(cargo=True,size=1)),
                                        ('preview_depot', dict(carrier='ROAD')),
                                        ('preview_depot', dict(carrier='TRAM'))])
def test_explicit_height_contract(command, extra):
    args = dict(x=0,y=30,rotation=0,**extra)
    validate_build_arguments(command, dict(args,z=1,frontage_node=10))
    with pytest.raises(ValueError):
        validate_build_arguments(command,dict(args,z=1))
    for z in (True, '1', float('nan'), float('inf')):
        with pytest.raises(ValueError):
            validate_build_arguments(command,dict(args,z=z,frontage_node=10))


@pytest.mark.parametrize('carrier', ['RAIL','WATER'])
def test_unsupported_depot_height_rejected(carrier):
    with pytest.raises(ValueError):
        validate_build_arguments('preview_depot', dict(x=0,y=30,z=1,rotation=0,carrier=carrier,frontage_node=10))
