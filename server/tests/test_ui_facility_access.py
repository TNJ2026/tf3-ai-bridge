"""Bounded native link inspection through real panel/events/logs; no live claims."""
import json

import pytest

from test_e2e import FakeGame, SCRIPT, bridge_dir
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments


def test_panel_access_readback_bounds_and_native_errors(bridge_dir, tmp_path):
    with FakeGame(bridge_dir) as game:
        lua, gui = game.lua, game.script
        lua.execute('''
          local CT=api.type.ComponentType
          CT.TP_NET_LINK=900;CT.BASE_EDGE_STREET=901
          components[220][CT.CONSTRUCTION].fileName="::/stations/air/heliport.con"
          components[9001]={[CT.BASE_EDGE]={node0=9002,node1=9003},[CT.BASE_EDGE_STREET]={}}
          components[9002]={[CT.BASE_NODE]={position={x=0,y=0,z=1}}}
          components[9003]={[CT.BASE_NODE]={position={x=20,y=0,z=1}}}
          components[9004]={[CT.TP_NET_LINK]={from={edgeId={entity=210,index=2}},to={edgeId={entity=9001,index=0}}}}
          components[9005]={[CT.TP_NET_LINK]={from={edgeId={entity=999,index=0}},to={edgeId={entity=9001,index=1}}}}
          LINK_MAP={{9004,9005},{9004}}
          api.engine.system.streetConnectorSystem.getConstructionEntityForSubconstruction=function(id)
            if id==210 then return 220 end
          end
          api.engine.system.tpNetLinkSystem={getEdgeId2linkEntities=function()return LINK_MAP end}
          api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)
            return {id=id,name=name,param=param}
          end
          api.cmd.sendCommand=function(cmd) forwarded=cmd end
        ''')
        state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
        log=tmp_path/'stdout.txt';log.touch()
        reader=UiLogRequests();output=[]
        lua.globals().print=lambda *args:output.append(' '.join(map(str,args)))

        def query(entity=220):
            ticket=reader.prepare_build(log,'get_facility_access',{'entity':entity})
            assert gui['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])=='Submitted; inspect log'
            event=lua.globals().forwarded
            fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
            fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
            with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
            output.clear()
            result=reader.read(ticket['id'])['response']
            assert not state['v']['uiConstruction']['pending']
            return result

        result=query()
        assert result['ok'],result
        data=result['result']
        assert data['complete'] and data['automaticRoadLinkObserved']
        assert len(data['links'])==1 and len(data['roads'])==1
        assert data['roads'][0]['position1']=={'x':20,'y':0,'z':1}
        assert not data['vehiclePathVerified'] and not data['sharedStockVerified']
        lua.execute('LINK_MAP={}')
        result=query()
        assert result['ok'] and not result['result']['automaticRoadLinkObserved']
        assert not query(999999)['ok']
        assert not query(9001)['ok']
        lua.execute('LINK_MAP={{9004}};components[9004][api.type.ComponentType.TP_NET_LINK]=nil')
        result=query()
        assert not result['ok'] and 'changed' in result['error']
        lua.execute('''
          LINK_MAP={{}}
          for n=1,129 do local id=10000+n;LINK_MAP[1][n]=id
            components[id]={[api.type.ComponentType.TP_NET_LINK]={from={edgeId={entity=220,index=0}},to={edgeId={entity=9001,index=0}}}}
          end
        ''')
        result=query()
        assert not result['ok'] and 'result limit' in result['error']
        lua.execute('api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities=function()error("native unavailable")end')
        result=query()
        assert not result['ok'] and 'native unavailable' in result['error']
        for bad in ({},{'entity':True},{'entity':220,'ignoreErrors':True}):
            with pytest.raises(ValueError):validate_build_arguments('get_facility_access',bad)
            raw='a'*32+' get_facility_access '+json.dumps(bad)
            assert gui['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',raw)!='Submitted; inspect log'
