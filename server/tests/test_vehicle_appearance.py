import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from test_ui_consolidated import Channel
from test_no_gui import host
from tf3_mcp.ui_log import validate_build_arguments
from tf3_mcp.vehicle_appearance import color_vehicles


FIXTURE = '''
local CT=api.type.ComponentType
CT.TRANSPORT_VEHICLE=CT.TRANSPORT_VEHICLE or 'TRANSPORT_VEHICLE'
CT.PLAYER_OWNED=CT.PLAYER_OWNED or 'PLAYER_OWNED'
components[9000]={[CT.PLAYER_OWNED]={player=api.engine.util.getPlayer()},
 [CT.TRANSPORT_VEHICLE]={line=10,transportVehicleConfig={vehicles={
 {part={modelId=1,color={x=.2,y=.3,z=.4}}},
 {part={modelId=2,color={x=.5,y=.6,z=.7}}}}}}}
api.res.modelRep.get=function(id)return {metadata={transportVehicle={noCblendMask=MASK or false}}} end
api.type.Vec3f.new=function(x,y,z)return {x=x,y=y,z=z}end
api.cmd.makeEntitySetColorCmd=function(id,color)return {paint=id,color=color}end
local old=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 if not cmd.paint then return old(cmd,cb) end
 if LOST then return end
 if REJECT then cb({},false);return end
 if not WRONG then
  for _,p in ipairs(components[cmd.paint][CT.TRANSPORT_VEHICLE].transportVehicleConfig.vehicles) do p.part.color=cmd.color end
 end
 cb({},true)
end
'''


def test_native_read_and_color(tmp_path):
    c = Channel(tmp_path, FIXTURE)
    before = c.query('get_vehicle_appearance', {'vehicle': 9000})
    assert before['ok'] and before['result']['canColor']
    result = c.query('set_vehicle_color', dict(vehicle=9000, r=.1, g=.2, b=.3))
    assert result['ok'], result
    assert result['result']['verified'] and c.lua.globals().dispatches == 1
    after = c.query('get_vehicle_appearance', {'vehicle': 9000})['result']
    assert all(p['color'] == {'r': .1, 'g': .2, 'b': .3} for p in after['parts'])
    assert c.state['v']['uiConstruction']['pending'] is None


@pytest.mark.parametrize('setup', ['MASK=true', 'components[9000][api.type.ComponentType.PLAYER_OWNED].player=999'])
def test_preflight_refuses_without_dispatch(tmp_path, setup):
    c = Channel(tmp_path, FIXTURE + setup)
    result = c.query('set_vehicle_color', dict(vehicle=9000, r=1, g=0, b=0))
    assert not result['ok'] and c.lua.globals().dispatches == 0
    assert c.state['v']['uiConstruction']['pending'] is None


@pytest.mark.parametrize('setup', ['WRONG=true', 'REJECT=true'])
def test_bad_callback_keeps_pending_and_blocks_next_write(tmp_path, setup):
    c = Channel(tmp_path, FIXTURE + setup)
    result = c.query('set_vehicle_color', dict(vehicle=9000, r=1, g=0, b=0))
    assert not result['ok']
    assert c.state['v']['uiConstruction']['pending']
    c.query('set_vehicle_color', dict(vehicle=9000, r=0, g=1, b=0))
    assert c.lua.globals().dispatches == 1


@pytest.mark.parametrize('value', [-.1, 1.1, True, float('nan'), float('inf')])
def test_invalid_rgb(value):
    with pytest.raises(ValueError):
        validate_build_arguments('set_vehicle_color', dict(vehicle=1, r=value, g=0, b=0))


def test_old_receiver_blocked(host):
    with pytest.raises(ValueError, match='vehicleAppearanceVersion'):
        host.send('set_vehicle_color', dict(vehicle=1, r=0, g=0, b=0), kind='build', expected_session='session')
    assert not host.ledger.exists()


def test_lost_callback_does_not_allow_second_dispatch(tmp_path):
    c = Channel(tmp_path, FIXTURE + 'LOST=true')
    # No response is emitted, so Channel's immediate response accessor has no key.
    with pytest.raises(KeyError):
        c.query('set_vehicle_color', dict(vehicle=9000, r=1, g=0, b=0))
    assert c.state['v']['uiConstruction']['pending']
    result = c.query('set_vehicle_color', dict(vehicle=9000, r=0, g=1, b=0))
    assert not result['ok'] and c.lua.globals().dispatches == 1


class Client:
    def __init__(self, path, fail=None):
        self.requests = SimpleNamespace(directory=path)
        self.session = 'test'
        self.fail = fail
        self.writes = []
        self.rows = {i: dict(vehicle=i, owner=2, line=10, complete=True, canColor=i != 3,
                        parts=[dict(modelId=i, colorable=i != 3, color=dict(r=0,g=0,b=0))])
                     for i in (1, 2, 3)}

    async def call(self, cmd, args):
        if cmd == 'get_game_state': return {'player': 2}
        if cmd == 'list_vehicles': return {'vehicles': [{'id': i} for i in self.rows]}
        if cmd == 'get_vehicle_appearance': return copy.deepcopy(self.rows[args['vehicle']])
        assert cmd == 'set_vehicle_color'
        self.writes.append(args['vehicle'])
        if args['vehicle'] == self.fail: raise TimeoutError('request original-id outcome unknown')
        self.rows[args['vehicle']]['parts'][0]['color'] = {k: args[k] for k in ('r','g','b')}
        return {'verified': True}


def test_bulk_stops_and_persists_partial_results(tmp_path):
    c = Client(tmp_path, fail=2)
    report = asyncio.run(color_vehicles(c, [1,2,3], 1,0,0))
    assert not report['complete'] and c.writes == [1,2]
    assert report['results'][0]['status'] == 'verified'
    saved = json.loads(__import__('pathlib').Path(report['journal']).read_text())
    assert saved['current'] == 2 and 'original-id' in saved['error']


def test_line_selection_and_unsupported_skip(tmp_path):
    c = Client(tmp_path)
    report = asyncio.run(color_vehicles(c, None, .3,.4,.5, line=10))
    assert report['complete'] and c.writes == [1,2]
    assert report['results'][-1]['status'] == 'skipped_no_color_mask'
