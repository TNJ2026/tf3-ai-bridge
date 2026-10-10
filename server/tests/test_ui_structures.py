"""Preview/commit building adapters using original handlers and mocked native API."""
import pytest
from test_e2e import FakeGame, SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments

CASES=[('preview_depot',dict(x=700,y=700,rotation=0,carrier=c)) for c in ['ROAD','TRAM','RAIL','WATER']]+[
 ('preview_station',dict(x=700,y=700,rotation=0,cargo=True,size=1)),
 ('preview_station',dict(x=700,y=700,rotation=0,cargo=False,size=2)),
 ('preview_rail_station',dict(x=700,y=700,rotation=0,tracks=2,length=160,specialization='universal')),
 ('preview_rail_station',dict(x=700,y=700,rotation=0,tracks=2,length=160,specialization='universal',cargo=False))]

@pytest.mark.parametrize('command,args',CASES)
@pytest.mark.parametrize('mode',['success','expired','blocked','lost','read_budget','full_budget'])
def test_structure_preview_commit(tmp_path,command,args,mode):
    game=FakeGame(tmp_path/'game');lua=game.lua;lua.globals().mode=mode
    lua.execute('''
      now=1;os.clock=function()return now end;mutations=0
      local send=api.cmd.sendCommand
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {event=true,id=id,name=name,param=param}end
      api.cmd.sendCommand=function(cmd,cb)
       if cmd.event then forwarded=cmd;return end
       mutations=mutations+1
       if mode=="lost" then return end
       send(cmd,function(...)
        -- Fixture construction builder predates ownership readback support.
        for _,c in pairs(components) do
         if c[api.type.ComponentType.CONSTRUCTION] and not c[api.type.ComponentType.PLAYER_OWNED] then
          c[api.type.ComponentType.PLAYER_OWNED]={player=api.engine.util.getPlayer()}
         end
        end
        cb(...)
       end)
      end
    ''')
    state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    if mode in ('read_budget','full_budget'):
        lua.globals().testState=state
        lua.execute("""
          local requests={}
          for i=1,256 do requests[tostring(i)]={cmd=(mode=='read_budget' and i<256) and 'get_entity' or 'commit_structure',status='returned'}end
          testState.v.uiConstruction={requests=requests,tokens={},count=256}
        """)
    log=tmp_path/'stdout.txt';log.touch();reader=UiLogRequests();output=[]
    lua.globals().print=lambda *v:output.append(' '.join(map(str,v)))
    def query(cmd,args):
        t=reader.prepare_build(log,cmd,args)
        assert game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',t['input'])=='Submitted; inspect log'
        e=lua.globals().forwarded;fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
        fresh['handleEvent'](None,state,'',e['id'],e['name'],e['param'])
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
        return e,reader.read(t['id'])['response']
    _,p=query(command,args)
    if mode=='full_budget':
        assert not p['ok'] and lua.globals().mutations==0
        assert state['v']['uiConstruction']['count']==256
        _,read=query('get_entity',{'id':220})
        assert read['ok'],read
        _,again=query(command,args)
        assert not again['ok'] and lua.globals().mutations==0
        assert state['v']['uiConstruction']['count']==256
        return
    assert p['ok'],p
    assert lua.globals().mutations==0
    assert p['result']['preview'] and not p['result']['externalConnectionsBuilt']
    token=p['result']['preview_token']
    if mode=='expired':lua.globals().now=100
    if mode=='blocked':
        lua.execute('api.engine.util.proposal.makeProposalData=function()error("native preview blocked")end')
    e,r=query('commit_structure',{'preview_token':token})
    assert r['ok']==(mode in ('success','read_budget')),r
    if mode in ('success','read_budget'):
        assert r['result']['built'] and r['result']['verified'] and not r['result']['externalConnectionsBuilt']
        assert lua.globals().mutations==1
        assert state['v']['uiConstruction']['pending'] is None
    elif mode=='lost':assert state['v']['uiConstruction']['pending']==r['id']
    else:assert lua.globals().mutations==0
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    fresh['handleEvent'](None,state,'',e['id'],e['name'],e['param'])
    before=lua.globals().mutations
    _,repeat=query('commit_structure',{'preview_token':token})
    assert not repeat['ok'] and lua.globals().mutations==before

@pytest.mark.parametrize('extra',[{'connect':True},{'preview':False},{'allow_collisions':True},{'carrier':'AIR'}])
def test_depot_bounds(extra):
    with pytest.raises(ValueError):validate_build_arguments('preview_depot',dict(CASES[0][1],**extra))
