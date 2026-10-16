import asyncio
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from test_vehicle_appearance import FIXTURE
from test_ui_consolidated import Channel
from tf3_mcp.repaint_builder import build_repaint
from tf3_mcp.appearance_sync import AppearanceSync
from tf3_mcp.ui_log import validate_build_arguments


V2 = FIXTURE + '''
local CT=api.type.ComponentType
components[1][CT.GAME_SPEED].speedup=0
components[2][CT.ACCOUNT].balance=20000000
local tv=components[9000][CT.TRANSPORT_VEHICLE];tv.state=0;tv.depot=300
tv.transportVehicleConfig.vehicleGroups={1,1};tv.transportVehicleConfig.muFileNames={}
for _,p in ipairs(tv.transportVehicleConfig.vehicles)do
 p.purchaseTime=123;p.maintenanceChange=0;p.maintenanceState=1;p.autoLoadConfig={}
 p.part.compartment2loadConfig={};p.part.reversed=false
end
api.engine.util.vehicle={getVehicleLoadedCargoTypes=function()return {}end,getPartPrice=function()return 100 end}
api.res.modelRep.get=function(id)return {metadata={description={name='Bus'},availability={yearFrom=1800,yearTo=0},cost={price=100},transportVehicle={noCblendMask=false,carrier=0,compartments={},groupFileName='original.mdl'}}}end
api.res.modelRep.find=function(name)return 3 end
api.res.modelRep.getName=function(id)return 'variant'..id..'.mdl' end
api.cmd.makeVehicleReplaceCmd=function(id,config)return {replace=id,config=config}end
local old=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 if not cmd.replace then return old(cmd,cb) end
 if not WRONG_REPLACE then components[cmd.replace][CT.TRANSPORT_VEHICLE].transportVehicleConfig=cmd.config end
 cb({},true)
end
'''


def test_reset_native_default(tmp_path):
    c = Channel(tmp_path, V2)
    result = c.query('reset_vehicle_color', {'vehicle':9000})
    assert result['ok'], result
    assert all(p['color']==dict(r=-1,g=-1,b=-1) for p in result['result']['after']['parts'])


def test_native_line_color_and_livery_catalog(tmp_path):
    c=Channel(tmp_path,V2+'''
      local CT=api.type.ComponentType;CT.COLOR=77
      components[10]={[CT.LINE]={},[CT.PLAYER_OWNED]={player=2},[CT.COLOR]={color={x=.1,y=.2,z=.3}}}
      api.engine.system.transportVehicleSystem.getLineVehicles=function()return {9000}end
      api.res.modelRep.forEachModelWithMetadata=function(_,cb)cb('variant3.mdl')end
    ''')
    line=c.query('get_line_appearance',{'line':10})
    assert line['ok'] and line['result']['color']==dict(r=.1,g=.2,b=.3)
    result=c.query('list_vehicle_liveries',dict(vehicle=9000,part=0))
    assert result['ok'] and result['result']['models'][0]['modelId']==3


@pytest.mark.parametrize('change', [dict(r=1,g=0,b=0), dict(reset=True), dict(model='variant3.mdl')])
def test_part_preview_and_commit_preserves_other_part(tmp_path, change):
    c = Channel(tmp_path, V2)
    before = c.query('get_vehicle_appearance', {'vehicle':9000})['result']
    preview = c.query('preview_vehicle_appearance', dict(vehicle=9000,part=1,**change))
    assert preview['ok'], preview
    # Preview must not mutate live components.
    assert c.query('get_vehicle_appearance', {'vehicle':9000})['result']==before
    result = c.query('commit_vehicle_appearance', dict(preview_token=preview['result']['preview_token'],
        backup_save='backup',max_cost=200,cash_floor=5000000))
    assert result['ok'], result
    assert result['result']['after']['parts'][0]==before['parts'][0]
    assert c.lua.globals().dispatches==1


def test_replacement_budget_rejected_without_mutation(tmp_path):
    c = Channel(tmp_path, V2)
    p = c.query('preview_vehicle_appearance', dict(vehicle=9000,part=0,r=1,g=0,b=0))['result']
    result = c.query('commit_vehicle_appearance', dict(preview_token=p['preview_token'],backup_save='backup',max_cost=10,cash_floor=5000000))
    assert not result['ok'] and c.lua.globals().dispatches==0


def test_replacement_readback_failure_keeps_pending(tmp_path):
    c = Channel(tmp_path, V2 + 'WRONG_REPLACE=true')
    p = c.query('preview_vehicle_appearance', dict(vehicle=9000,part=0,r=1,g=0,b=0))['result']
    result = c.query('commit_vehicle_appearance', dict(preview_token=p['preview_token'],backup_save='backup',max_cost=200,cash_floor=5000000))
    assert not result['ok'] and c.state['v']['uiConstruction']['pending']


def test_preview_invalidated_by_live_config_change(tmp_path):
    c = Channel(tmp_path, V2)
    p = c.query('preview_vehicle_appearance', dict(vehicle=9000,part=0,r=1,g=0,b=0))['result']
    c.lua.execute('components[9000][api.type.ComponentType.TRANSPORT_VEHICLE].transportVehicleConfig.vehicles[1].purchaseTime=999')
    result = c.query('commit_vehicle_appearance', dict(preview_token=p['preview_token'],backup_save='backup',max_cost=200,cash_floor=5000000))
    assert not result['ok'] and c.lua.globals().dispatches==0


def test_mechanical_difference_is_not_accepted_as_livery(tmp_path):
    c = Channel(tmp_path, V2 + '''
      local get=api.res.modelRep.get
      api.res.modelRep.get=function(id)local r=get(id);r.metadata.landVehicle={topSpeed=id==3 and 99 or 10};return r end
    ''')
    result = c.query('preview_vehicle_appearance', dict(vehicle=9000,part=0,model='variant3.mdl'))
    assert not result['ok'] and c.lua.globals().dispatches==0


def test_native_sync_guard_refuses_moved_vehicle(tmp_path):
    c = Channel(tmp_path, V2)
    result = c.query('set_vehicle_color', dict(vehicle=9000,r=1,g=0,b=0,expected_line=999))
    assert not result['ok'] and c.lua.globals().dispatches==0


@pytest.mark.parametrize('args', [dict(r=1),dict(r=1,g=0,b=0,reset=True),dict(model='x',reset=True),{}])
def test_preview_exclusive_parameters(args):
    with pytest.raises(ValueError):
        validate_build_arguments('preview_vehicle_appearance',dict(vehicle=1,part=0,**args))


def test_repaint_builds_separate_resources_without_executing_lua(tmp_path):
    archive = tmp_path/'bus.zip'
    stream = io.BytesIO();Image.new('RGBA',(32,32),'blue').save(stream,format='PNG')
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('bus/bus.mdl','function data() return {lods={{materials={"mat/body.mtl"},mesh="msh/body.msh"}},metadata={description={},transportVehicle={}}} end')
        z.writestr('bus/mat/body.mtl','function data() return {params={map_albedo={fragmentSamplers={albedoTex={fileName="tex/body.png"}}},map_normal={fileName="tex/normal.dds"}}} end')
        z.writestr('bus/mat/tex/body.png',stream.getvalue())
    out=tmp_path/'repaint'
    result=build_repaint(archive,'bus/bus.mdl','::/vehicle/bus/bus.mdl','bus/mat/tex/body.png',out,'custom_repaint','Bus Red', [{'text':'AD','box':[0,0,32,16],'color':'red'}])
    assert not result['installed'] and result['changedMaterials']==1
    mdl=(out/'content/vehicle/repaint/repaint.mdl').read_text()
    assert 'custom_repaint::/vehicle/repaint/material_0.mtl' in mdl
    assert '::/vehicle/bus/msh/body.msh' in mdl
    mtl=(out/'content/vehicle/repaint/material_0.mtl').read_text()
    assert 'custom_repaint::/vehicle/repaint/albedo.tga' in mtl
    assert '::/vehicle/bus/mat/tex/normal.dds' in mtl
    with pytest.raises(ValueError,match='new directory'):
        build_repaint(archive,'bus/bus.mdl','::/vehicle/bus/bus.mdl','bus/tex/body.png',out,'custom_repaint','Bus Red')


@pytest.mark.parametrize('extension', ['dds', 'png'])
def test_repaint_converts_dds_vertical_convention_only(tmp_path, extension):
    atlas = Image.new('RGBA', (8, 8), 'blue')
    for x in range(8):
        atlas.putpixel((x, 0), (255, 0, 0, 255))
    stream = io.BytesIO()
    atlas.save(stream, format=extension.upper())
    archive = tmp_path/'bus.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('bus/bus.mdl', 'function data() return {lods={{materials={"body.mtl"}}},metadata={description={},transportVehicle={}}} end')
        z.writestr('bus/body.mtl', 'function data() return {albedoTex={fileName="body.'+extension+'"}} end')
        z.writestr('bus/body.'+extension, stream.getvalue())
    replacement = tmp_path/'replacement.png'
    atlas.save(replacement)
    out = tmp_path/'mod'
    result = build_repaint(archive, 'bus/bus.mdl', '::/vehicle/bus/bus.mdl',
                           'bus/body.'+extension, out, 'orientation_test', 'Test',
                           replacement_image=replacement)
    exported = Image.open(out/'content/vehicle/repaint/albedo.tga').convert('RGBA')
    assert exported.getpixel((0, 7 if extension == 'dds' else 0)) == (255, 0, 0, 255)
    assert result['tgaFlippedFromDDS'] == (extension == 'dds')
    assert Image.open(out/'atlas_preview.png').getpixel((0, 0)) == (255, 0, 0, 255)


def test_sync_noop_and_session_guard(tmp_path):
    class Client:
        requests=SimpleNamespace(directory=tmp_path)
        async def status(self):return {'receiver':{'session':'s','vehicleAppearanceVersion':2},'pending':None}
        async def call(self,cmd,args):
            if cmd=='get_line_appearance':return dict(color=dict(r=1,g=0,b=0),vehicles=[3])
            assert cmd=='get_vehicle_appearance'
            return dict(line=1,complete=True,canColor=True,parts=[dict(colorable=True,color=dict(r=1,g=0,b=0))])
    sync=AppearanceSync(Client());sync.data.update(session='s',lines=[1])
    asyncio.run(sync.once());assert sync.data['lastChanges']==[]
    sync.data['session']='other'
    with pytest.raises(ValueError,match='Session'):
        asyncio.run(sync.once())


def test_sync_changed_color_and_new_vehicle(monkeypatch, tmp_path):
    calls=[]
    class Client:
        requests=SimpleNamespace(directory=tmp_path)
        vehicles=[3]
        color=dict(r=1,g=0,b=0)
        async def status(self):return {'receiver':{'session':'s','vehicleAppearanceVersion':2},'pending':None}
        async def call(self,cmd,args):
            if cmd=='get_line_appearance':return dict(color=self.color,vehicles=self.vehicles)
            return dict(line=1,complete=True,canColor=True,parts=[dict(colorable=True,color=dict(r=0,g=0,b=0))])
    async def change(client, vehicles, **kwargs):
        calls.append((vehicles,kwargs));return dict(complete=True,journal='receipt')
    monkeypatch.setattr('tf3_mcp.appearance_sync.color_vehicles',change)
    client=Client();sync=AppearanceSync(client);sync.data.update(session='s',lines=[1])
    asyncio.run(sync.once())
    client.vehicles=[3,4];client.color=dict(r=0,g=1,b=0)
    asyncio.run(sync.once())
    assert [c[0] for c in calls]==[[3],[3],[4]]
    assert calls[-1][1]['g']==1 and calls[-1][1]['expected_line']==1


def test_sync_start_stop_and_restart_never_autostarts(tmp_path):
    class Client:
        requests=SimpleNamespace(directory=tmp_path)
        async def status(self):return {'receiver':{'session':'s','vehicleAppearanceVersion':2},'pending':None}
        async def call(self,cmd,args):return dict(color=dict(r=1,g=0,b=0),vehicles=[])
    async def exercise():
        sync=AppearanceSync(Client())
        await sync.start([1],10)
        await asyncio.sleep(.02)
        result=await sync.stop()
        assert not result['running'] and not result['active']
        assert AppearanceSync(Client()).status()['active'] is False
    asyncio.run(exercise())
