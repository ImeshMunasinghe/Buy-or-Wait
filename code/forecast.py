from datetime import date, timedelta
from calendar import monthrange

def add_months(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))

def month_day(y, m, day):
    return date(y, m, min(day, monthrange(y, m)[1]))

def _dates(start, n):
    return [start + timedelta(days=i) for i in range(n + 1)]

def build_flows(ctx, request_date, changes=None):
    changes = changes or []
    stopped = {c[1] for c in changes if c[0] == "stop"}
    reduced = {c[1]: c[2] for c in changes if c[0] == "reduce"}
    flows = {}
    horizon = request_date + timedelta(days=200)
    def add(d, v):
        if request_date <= d <= horizon:
            flows[d] = flows.get(d, 0.0) + v
    base = date(request_date.year, request_date.month, 1)
    for it in ctx.monthlies:
        if it["event_id"] in stopped: continue
        amt = it["amount"]
        if it["event_id"] in reduced:
            amt = max(it["min_allowed"], reduced[it["event_id"]])
        for k in range(0, 7):
            d0 = add_months(base, k)
            add(month_day(d0.year, d0.month, it["day"]), -amt)
    for s in ctx.salary_streams:
        for k in range(0, 7):
            d0 = add_months(base, k)
            d = month_day(d0.year, d0.month, s["day"])
            amt = s["amount"]
            for eff, new_amt in sorted(s.get("overrides", [])):
                if d >= eff: amt = new_amt
            stop_after = s.get("stop_after")
            if stop_after and d > stop_after: amt = 0.0
            if amt: add(d, amt)
    for d, amt in ctx.extra_credits: add(d, amt)
    for d, amt, eid in ctx.oneoff_debits: add(d, -amt)
    rate = getattr(ctx, "var_daily_rate", 0.0)
    if rate:
        d = request_date
        while d <= horizon:
            add(d, -rate)
            d += timedelta(days=1)
    return flows

def project(flows, balance0, request_date):
    out = {}
    bal = balance0
    d = request_date
    horizon = request_date + timedelta(days=200)
    while d <= horizon:
        bal += flows.get(d, 0.0)
        out[d] = bal
        d += timedelta(days=1)
    return out

def simulate(flows, balance0, request_date, payments):
    pay = {}
    for d, a in payments: pay[d] = pay.get(d, 0.0) + a
    out = {}
    bal = balance0
    d = request_date
    horizon = request_date + timedelta(days=200)
    while d <= horizon:
        bal += flows.get(d, 0.0) - pay.get(d, 0.0)
        out[d] = bal
        d += timedelta(days=1)
    return out

def safe_amount(flows, balance0, request_date, min_balance, cap):
    """Binary-search for the largest amount payable on request_date that keeps
    the simulated balance >= min_balance for the next 90 days."""
    if cap <= 0:
        return 0.0
    # Quick check: can we pay anything at all?
    sim0 = simulate(flows, balance0, request_date, [(request_date, 1e-9)])
    vals0 = [sim0[d] for d in _dates(request_date, 90) if d in sim0]
    if not vals0 or min(vals0) < min_balance - 1e-9:
        return 0.0
    lo, hi = 0.0, cap
    for _ in range(60):
        mid = (lo + hi) / 2.0
        sim = simulate(flows, balance0, request_date, [(request_date, mid)])
        vals = [sim[d] for d in _dates(request_date, 90) if d in sim]
        if vals and min(vals) >= min_balance - 1e-9:
            lo = mid
        else:
            hi = mid
    return round(lo, 2) if lo > 1e-9 else 0.0

def earliest_full_date(flows, balance0, request_date, min_balance, amount, window_days=180):
    """First date when paying 'amount' keeps simulated balance >= min_balance for 90 days."""
    for i in range(window_days + 1):
        pay_date = request_date + timedelta(days=i)
        sim = simulate(flows, balance0, request_date, [(pay_date, amount)])
        ok = True
        for j in range(91):
            dd = pay_date + timedelta(days=j)
            if dd in sim and sim[dd] < min_balance - 1e-9:
                ok = False
                break
        if ok:
            return pay_date
    return None
