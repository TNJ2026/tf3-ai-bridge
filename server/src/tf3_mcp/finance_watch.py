"""Account-level monitoring; never reconstruct transactions from cash changes."""
import math


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def assess(current, previous=None, cash_floor=1_500_000):
    finances = current['finances']
    balance = finances.get('balance', current['state'].get('balance'))
    debt = finances.get('loan')
    # The current native adapter exposes no income statistic. Accept only an
    # explicitly labelled native field; cash changes include spending and loans.
    income = finances.get('income')
    income_known = number(income) and bool(finances.get('incomePeriod'))
    old = previous.get('accountWatch', {}) if previous else {}
    now_time = current['state'].get('gameTime')
    old_time = previous['state'].get('gameTime') if previous else None
    advanced = number(now_time) and number(old_time) and now_time > old_time
    comparable = (previous is not None and current['session'] == previous['session']
                  and current['state'].get('player') == previous['state'].get('player')
                  and current.get('mapDigest') == previous.get('mapDigest')
                  and number(now_time) and number(old_time) and now_time >= old_time)
    if not comparable:
        old = {}
    delta = balance - old['balance'] if advanced and comparable and number(balance) and number(old.get('balance')) else None
    falling = (old.get('fallingSamples', 0) + 1 if delta < 0 else 0) if delta is not None else old.get('fallingSamples', 0)
    risks = []
    if not number(balance):
        risks.append('balance_unknown')
    elif balance < 0:
        risks.append('negative_cash')
    elif balance <= cash_floor:
        risks.append('cash_reserve_low')
    if falling >= 2:
        risks.append('cash_falling')
    if number(debt) and number(old.get('debt')) and debt > old['debt']:
        risks.append('debt_increased')
    watch = dict(balance=balance, debt=debt, income=income if income_known else None,
                 incomePeriod=finances.get('incomePeriod') if income_known else None,
                 incomeStatus='native' if income_known else 'unavailable',
                 cashFloor=cash_floor, cashChange=delta, fallingSamples=falling,
                 risks=risks, paidActionsAllowed=number(balance) and balance > cash_floor,
                 basis='cash change is not income; no transaction reconciliation')
    events = [dict(type=r, balance=balance, debt=debt) for r in risks if r not in old.get('risks', [])]
    if old.get('risks') and not risks:
        events.append(dict(type='account_risk_recovered', balance=balance))
    return watch, events
