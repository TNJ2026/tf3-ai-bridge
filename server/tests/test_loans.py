"""Exercise real loan bridge code; no live borrowing or repayment."""
import json

import pytest

from test_e2e import MOCK_API, SCRIPT, lupa_mod


FIXTURE = r'''
local CT=api.type.ComponentType
CT.GAME_SCRIPT=110
NOW=100
os.clock=function()return NOW end
LOANS={freeId=0,availableLoans={
 {type="Small",amount=9000000,duration=36000,percentage=.03,birthDay=120000},
 {type="Medium",cooldownUntil=999999}},obtainedLoans={}}
components[9000]={[110]={state=LOANS}}
api.engine.system.gameScriptSystem={getEntityForGameScript=function()return 9000 end}
api.util={getDefaultYearDuration=function()return 12000 end}
api.engine.util.finance={getPlayersBalance=function()
 if INFINITE then return nil end
 return components[2][6].balance
end}
local util={maximalObtainableLoans=4,
 getDurationInMonths=function(d)return d/1000 end,
 getMonthlyLoanAndInterestWithErrors=function(a,d,p)return a/(d/1000),a*p/(d/1000) end,
 getFullLoanAndInterestPayBack=function(l)return l.amount*(1-l.timesPaid/(l.duration/1000)),l.amount*l.percentage end}
ug_require=function(path)assert(path=="::/game_mechanics/finance/loan_util.tl");return util end
SEND_COUNT=0
api.cmd.makeScriptingSendEventCmd=function(src,id,name,payload)
 assert(src=="" and id=="Loan")
 return {name=name,payload=payload}
end
function DELIVER(cmd)
 local loan=cmd.payload[2]
 if cmd.name=="Obtain" then
  assert(cmd.payload[1].type==loan.type)
  local got={id=LOANS.freeId,type=loan.type,amount=loan.amount,duration=loan.duration,
   percentage=loan.percentage,lastPayDay=components[1][4].gameTime,timesPaid=0}
  LOANS.obtainedLoans[#LOANS.obtainedLoans+1]=got
  LOANS.freeId=LOANS.freeId+1
  components[2][6].balance=components[2][6].balance+loan.amount
  LOANS.availableLoans[1]={type=loan.type,cooldownUntil=999999}
 else
  assert(cmd.payload[1]==nil)
  components[2][6].balance=components[2][6].balance-util.getFullLoanAndInterestPayBack(loan)
  for i,l in ipairs(LOANS.obtainedLoans)do if l.id==loan.id then table.remove(LOANS.obtainedLoans,i);break end end
 end
end
api.cmd.sendCommand=function(cmd,cb)
 SEND_COUNT=SEND_COUNT+1
 if DISPATCH_ERROR then error("dispatch outcome unknown") end
 if FAIL then cb({},false);return end
 if DELAY then PENDING=cmd else DELIVER(cmd) end
 cb({},true)
end
'''


@pytest.fixture
def game():
    lua=lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(FIXTURE)
    script=lua.execute(SCRIPT.read_text(encoding="utf8"))
    def call(name, **args):
        result=script["_internal"]["commands"][name](lua.table_from(args, recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](result))
    return lua,call


def borrow(call):
    return call("preview_loan",action="borrow",offer_type="Small")["preview_token"]


def test_queries_and_previews_do_not_mutate(game):
    lua,call=game
    loans=call("get_loans")
    assert loans["available"][0]["monthlyPayment"]==257500
    assert loans["maxObtained"]==4 and not loans["infiniteMoney"]
    preview=call("preview_loan",action="borrow",offer_type="Small")
    assert preview["cashChange"]==9000000 and preview["durationMonths"]==36
    assert lua.globals().SEND_COUNT==0
    assert lua.globals().LOANS.freeId==0


def test_borrow_repay_and_one_time_tokens(game):
    lua,call=game
    token=borrow(call)
    got=call("commit_loan",preview_token=token)
    assert got["verified"] and got["loan_id"]==0 and got["cashMatches"]
    with pytest.raises(Exception,match="consumed"):
        call("commit_loan",preview_token=token)
    p=call("preview_loan",action="repay",loan_id=0)
    assert p["cashChange"]==-9000000
    assert call("commit_loan",preview_token=p["preview_token"])["verified"]
    assert call("get_loans")["obtained"]==[]
    assert lua.globals().SEND_COUNT==2
    assert call("get_loan_operation",operation_id=token)["verified"]  # stable historical receipt


@pytest.mark.parametrize("setup,error",[
    ("LOANS.availableLoans[1].cooldownUntil=999999", "cooldown"),
    ("LOANS.availableLoans[1].birthDay=0", "expired"),
    ("INFINITE=true", "infinite"),
    ("LOANS.obtainedLoans={{},{},{},{}}", "maximum"),
])
def test_ineligible_borrow_never_dispatches(game,setup,error):
    lua,call=game
    lua.execute(setup)
    with pytest.raises(Exception,match=error):borrow(call)
    assert lua.globals().SEND_COUNT==0


@pytest.mark.parametrize("change,error",[
    ("LOANS.availableLoans[1].amount=10000000", "changed"),
    ("LOANS.availableLoans[1].percentage=.08", "changed"),
    ("LOANS.freeId=1", "changed"),
    ("components[1][4].gameTime=1", "changed"),
    ("NOW=161", "expired"),
])
def test_stale_preview_rejected(game,change,error):
    lua,call=game
    token=borrow(call)
    lua.execute(change)
    with pytest.raises(Exception,match=error):call("commit_loan",preview_token=token)
    assert lua.globals().SEND_COUNT==0


def test_repayment_rechecks_cash_and_paid_installments(game):
    lua,call=game
    call("commit_loan",preview_token=borrow(call))
    p=call("preview_loan",action="repay",loan_id=0)
    lua.execute("components[2][6].balance=1")
    with pytest.raises(Exception,match="insufficient"):
        call("commit_loan",preview_token=p["preview_token"])
    lua.execute("components[2][6].balance=20000000")
    p=call("preview_loan",action="repay",loan_id=0)
    lua.execute("LOANS.obtainedLoans[1].timesPaid=1")
    with pytest.raises(Exception,match="changed"):
        call("commit_loan",preview_token=p["preview_token"])
    assert lua.globals().SEND_COUNT==1


def test_delayed_event_is_reconciled_without_resending(game):
    lua,call=game
    lua.execute("DELAY=true")
    token=borrow(call)
    r=call("commit_loan",preview_token=token)
    assert r["status"]=="needs_reconciliation" and not r["verified"]
    second=borrow(call)
    with pytest.raises(Exception,match="previous"):
        call("commit_loan",preview_token=second)
    lua.execute("DELIVER(PENDING)")
    assert call("get_loan_operation",operation_id=token)["verified"]
    assert lua.globals().SEND_COUNT==1


@pytest.mark.parametrize("setup",["FAIL=true","DISPATCH_ERROR=true"])
def test_failed_dispatch_is_not_retried(game,setup):
    lua,call=game
    lua.execute(setup)
    token=borrow(call)
    r=call("commit_loan",preview_token=token)
    assert not r["verified"] and r["status"]=="needs_reconciliation"
    with pytest.raises(Exception,match="consumed"):
        call("commit_loan",preview_token=token)
    assert lua.globals().SEND_COUNT==1


def test_cash_mismatch_prevents_false_verification(game):
    lua,call=game
    lua.execute("DELAY=true")
    token=borrow(call)
    call("commit_loan",preview_token=token)
    lua.execute("DELIVER(PENDING);components[2][6].balance=components[2][6].balance-100")
    r=call("get_loan_operation",operation_id=token)
    assert r["loanRecordMatches"] and not r["cashMatches"] and not r["verified"]


def test_mcp_routes_to_engine(monkeypatch):
    import asyncio
    from tf3_mcp import server
    seen=[]
    async def fake(cmd,**args):seen.append((cmd,args));return {}
    monkeypatch.setattr(server,"_call",fake)
    async def run():
        await server.get_loans()
        await server.preview_loan("borrow",offer_type="Small")
        await server.commit_loan("a")
        await server.get_loan_operation("a")
    asyncio.run(run())
    assert [r[0] for r in seen]==["get_loans","preview_loan","commit_loan","get_loan_operation"]
    assert all(r[1]["_engine"] for r in seen)
