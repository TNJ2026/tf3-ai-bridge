"""Tram frontage cannot silently replace roads lacking electric tram lanes."""
import pytest
from lupa import LuaError
from test_ui_frontage import frontage


def test_tram_frontage_requires_bidirectional_electric_lanes(frontage):
    lua,a=frontage
    with pytest.raises(LuaError,match='both directions'):
        a['bind'](lua.eval('{streetProposal={}}'),10,'TRAM')
    assert lua.globals().previews==0
    lua.execute('''
      for _,e in pairs(edges) do
       e.laneConfigs={{offset=0,width=3,height=0,speed=20,forward=true,transportModes={[5]=true,[6]=true}},
        {offset=0,width=3,height=0,speed=20,forward=false,transportModes={[5]=true,[6]=true}}}
      end
      local original=previewProposal
      previewProposal=function(p)
       local check,data=original(p)
       for _,net in pairs(data.entity2tn) do for _,e in ipairs(net.edges) do
        e.transportModes={[5]=true,[6]=true}
       end end
       return check,data
      end
    ''')
    p,result,check=a['bind'](lua.eval('{streetProposal={}}'),10,'TRAM')
    assert check['ok'] and result['nativeEntranceNode']==-8
    assert p['streetProposal']['edgesToAdd'][1]['comp']['laneConfigs'][1]['transportModes'][6]
    for cfg in p['streetProposal']['nodeConfigsToAdd'].values():
        assert list(cfg['comp']['crosswalks'].values())==[-3,-4]
    lua.execute('edges[21].laneConfigs[2].transportModes[6]=false')
    with pytest.raises(LuaError,match='both directions'):
        a['bind'](lua.eval('{streetProposal={}}'),10,'TRAM')
