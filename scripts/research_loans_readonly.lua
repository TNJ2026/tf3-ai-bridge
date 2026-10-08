-- Research only: no commands, event dispatch, state writes or random loan generation.
local CT=api.type.ComponentType
local entity=api.engine.system.gameScriptSystem.getEntityForGameScript("::/game_mechanics/finance/loan.gs")
assert(entity and entity>=0,"native loan script not found")
local component=api.engine.getComponent(entity,CT.GAME_SCRIPT)
assert(component,"loan script component unavailable")
local loanTable=component.state
local util=ug_require("::/game_mechanics/finance/loan_util.tl")
local out={state=B.commands.get_game_state(),scriptEntity=entity,available={},obtained={},freeId=loanTable.freeId,
 eventConstructorType=type(api.cmd.makeScriptingSendEventCmd),maxObtained=util.maximalObtainableLoans,
 defaultMonthDuration=api.util.getDefaultMonthDuration(),defaultYearDuration=api.util.getDefaultYearDuration()}
local balance=api.engine.util.finance.getPlayersBalance(api.engine.util.getPlayer())
out.infiniteMoney=balance==nil
local function row(v)
 local r={}
 for _,k in ipairs({"id","type","amount","duration","percentage","lastPayDay","timesPaid","birthDay","cooldownUntil"}) do r[k]=v[k] end
 if r.amount then
  r.displayAmount=api.util.formatMoney(r.amount)
  r.durationMonths=util.getDurationInMonths(r.duration)
  local principal,interest=util.getMonthlyLoanAndInterestWithErrors(r.amount,r.duration,r.percentage)
  r.monthlyPrincipal=principal;r.monthlyInterest=interest
  r.monthlyTotalDisplay=api.util.formatMoney(principal+interest)
  if r.timesPaid~=nil then local p,i=util.getFullLoanAndInterestPayBack(v);r.earlyRepaymentPrincipal=p;r.remainingScheduledInterest=i end
 end
 return r
end
for _,v in ipairs(loanTable.availableLoans) do out.available[#out.available+1]=row(v) end
for _,v in ipairs(loanTable.obtainedLoans) do out.obtained[#out.obtained+1]=row(v) end
return B.json.encode(out)
