-- Real-game smoke check: queries and local previews only; never commit a loan.
local before=B.commands.get_loans({})
local out={before=before,borrowPreviews={},repayPreviews={}}
for _,offer in ipairs(before.available) do
 if offer.amount and not offer.cooldownUntil and offer.type~="Custom" then
  local ok,result=pcall(B.commands.preview_loan,{action="borrow",offer_type=offer.type})
  out.borrowPreviews[#out.borrowPreviews+1]={ok=ok,result=result}
 end
end
for _,loan in ipairs(before.obtained) do
 local ok,result=pcall(B.commands.preview_loan,{action="repay",loan_id=loan.id})
 out.repayPreviews[#out.repayPreviews+1]={ok=ok,result=result}
end
out.after=B.commands.get_loans({})
out.balanceUnchanged=out.after.balance==before.balance
out.loanCountUnchanged=#out.after.obtained==#before.obtained and out.after.freeId==before.freeId
return B.json.encode(out)
