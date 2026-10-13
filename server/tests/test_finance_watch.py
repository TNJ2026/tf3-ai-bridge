import asyncio
from tf3_mcp.finance_watch import assess
from tf3_mcp.headless_workflows import OperationsMonitor


def sample(balance, t=1, session='s', **finance):
    return dict(session=session,mapDigest='map',state=dict(player=1,gameTime=t,balance=balance),
                finances=dict(balance=balance,loan=35000000,**finance))


def evaluated(value, old=None):
    value['accountWatch'], events=assess(value,old)
    return value, events


def test_cash_change_never_fabricates_income_and_pause_is_not_a_trend():
    a,_=evaluated(sample(4000000))
    b,_=evaluated(sample(3900000,2),a)
    c,_=evaluated(sample(3900000,2),b)
    assert b['accountWatch']['cashChange']==-100000
    assert b['accountWatch']['income'] is None
    assert c['accountWatch']['cashChange'] is None
    assert c['accountWatch']['fallingSamples']==1
    d,events=evaluated(sample(3800000,3),c)
    assert any(e['type']=='cash_falling' for e in events)
    assert d['accountWatch']['fallingSamples']==2


def test_floor_missing_income_and_session_reset():
    a,events=evaluated(sample(1500000,income=123))
    assert not a['accountWatch']['paidActionsAllowed']
    assert a['accountWatch']['income'] is None  # No period, no income claim.
    assert events[0]['type']=='cash_reserve_low'
    b,events=evaluated(sample(1500000,1),a)
    assert events==[]
    c,_=evaluated(sample(1000000,2,'new'),b)
    assert c['accountWatch']['cashChange'] is None
    d,_=evaluated(sample(None))
    assert not d['accountWatch']['paidActionsAllowed']


def test_monitor_queries_only_account_and_identity_and_stays_stopped(tmp_path):
    class Client:
        session='s'
        def __init__(self): self.lock=asyncio.Lock();self.calls=[]
        async def status(self): return {'pending':None}
        def map_digest(self,world):return 'map'
        async def request(self,command,args):
            self.calls.append(command)
            return {'get_game_state':dict(player=1,gameTime=1,balance=2000000),
                    'get_map_info':dict(towns=[]),
                    'get_finances':dict(balance=2000000,loan=35000000)}[command]
    async def run():
        client=Client();monitor=OperationsMonitor(client,tmp_path)
        await monitor.once()
        assert client.calls==['get_game_state','get_map_info','get_finances']
        assert not monitor.status()['running']
        assert monitor.previous['accountWatch']['incomeStatus']=='unavailable'
    asyncio.run(run())
