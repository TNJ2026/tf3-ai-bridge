"""Large native facility records must fit the no_gui reply and paginate losslessly."""
import json
import pytest
from test_ui_consolidated import Channel, FACILITY
from test_facilities import game
from tf3_mcp.ui_log import validate_build_arguments


def test_large_config_paged_on_new_channel(tmp_path):
    c=Channel(tmp_path,FACILITY)
    c.lua.execute("""
PARAMS.custom.payload=string.rep('large native metadata',6000)
local slots=components[8000][api.type.ComponentType.CONSTRUCTION].slots
for i=12,90 do slots[#slots+1]={id=i,type='storage',replaceable=true} end
for i=12,80 do PARAMS.modules[i]={name='::/warehouses/a.module',variant=0} end
api.res.moduleRep.getAll=function()local t={};for i=0,94 do t[i]='module'..i end;return t end
api.res.moduleRep.get=function(id)return {type='storage',availability={yearFrom=1900,yearTo=0}} end
""")
    slots=[];modules={};compatible=[]
    for offset in range(0,100,10):
        reply=c.query('get_facility_config',{'entity':8000,'offset':offset,'limit':10})
        assert reply['ok'],reply
        r=reply['result']
        assert len(json.dumps(reply))<65536
        assert r['compact'] and 'custom' not in r['params']
        slots.extend(s['id'] for s in r['slots'])
        modules.update(r['params']['modules'] or {})
        compatible.extend(m['resource'] for m in r['compatible_modules'])
        assert r['hasMore']==(offset+10<95)
        assert (r['slotCount'],r['moduleCount'],r['compatibleModuleCount'])==(81,70,95)
    assert len(set(slots))==81 and len(modules)==70 and len(set(compatible))==95
    assert c.lua.globals().dispatches==0
    assert not c.state['v']['uiConstruction']['pending']


def test_legacy_config_keeps_nested_parameters(game):
    _,call=game
    assert call('get_facility_config',entity=8000)['params']['custom']['important']==['preserve',4]


@pytest.mark.parametrize('args',[{'entity':8000}, {'entity':8000,'offset':10,'limit':1}])
def test_config_optional_page_schema(args):
    validate_build_arguments('get_facility_config',args)


@pytest.mark.parametrize('args',[{'entity':8000,'offset':-1}, {'entity':8000,'limit':0}])
def test_invalid_config_page_schema(args):
    with pytest.raises(ValueError):
        validate_build_arguments('get_facility_config',args)
