from datetime import date, timedelta
from calendar import monthrange
import loader
import forecast as F

def var_daily_rate(ctx, request_date):
    return 0.0
def fmt_d(d): return d.isoformat()

class Req:
    def __init__(self, row):
        if isinstance(row, Req):
            self.id, self.uid, self.rd = row.id, row.uid, row.rd
            self.amount, self.deadline = row.amount, row.deadline
            self.allows_partial = row.allows_partial
            return
        self.id = row["request_id"]
        self.uid = row["user_id"]
        self.rd = loader.pdate(row["request_date"])
        self.amount = loader.pfloat(row["requested_amount"])
        self.deadline = loader.pdate(row["desired_completion_date"])
        self.allows_partial = row["allows_partial_payment"].strip().lower() in ("true", "yes", "1")

def build_candidates(ctx, req, opts, changes):
    A = req.amount
    rd = req.rd
    minb = ctx.min_balance
    ctx.var_daily_rate = var_daily_rate(ctx, rd)
    flows = F.build_flows(ctx, rd, changes)
    proj = F.project(flows, ctx.balance, rd)
    horizon = rd + timedelta(days=180)
    deadline = req.deadline or (rd + timedelta(days=90))
    cands = []
    safe = F.safe_amount(proj, rd, minb, A)
    eps = 1e-6
    def pay_ok(payments):
        sim = F.simulate(flows, ctx.balance, rd, payments)
        last = max(d for d, a in payments)
        end = min(last + timedelta(days=90), rd + timedelta(days=200))
        d = rd
        while d <= end:
            if d in sim and sim[d] < minb - eps: return False
            d += timedelta(days=1)
        return True
    if A > 0 and safe >= A - eps:
        if pay_ok([(rd, A)]):
            cands.append({"kind": "full", "method": "full_payment", "status": "affordable_now",
                          "safe": safe, "payments": [(rd, A)], "cost": A, "changes": list(changes),
                          "complete": rd, "start": rd, "opt": "", "earliest": rd})
    if A > 0:
        if "full_payment" in ctx.methods:
            t = F.earliest_full_date(proj, rd, minb, A, 180)
            if t and t <= deadline and t <= horizon and pay_ok([(t, A)]):
                cands.append({"kind": "wait", "method": "wait", "status": "affordable_later",
                              "safe": safe, "payments": [(t, A)], "cost": A, "changes": list(changes),
                              "complete": t, "start": t, "opt": "", "earliest": t})
        if req.allows_partial and "partial_payment" in ctx.methods and 0 < safe < A - eps:
            rest = A - safe
            t = F.earliest_full_date(proj, rd + timedelta(days=1), minb, rest, 180)
            if t and t <= deadline and t <= horizon and pay_ok([(rd, safe), (t, rest)]):
                cands.append({"kind": "partial", "method": "partial_payment",
                              "status": "affordable_with_plan", "safe": safe,
                              "payments": [(rd, safe), (t, rest)], "cost": A,
                              "changes": list(changes), "complete": t, "start": rd, "opt": "",
                              "earliest": F.earliest_full_date(proj, rd, minb, A, 180) or t})
        if "installments" in ctx.methods:
            for o in opts:
                pm = o["payment_method"].strip()
                if pm != "installments": continue
                n = int(o["number_of_payments"])
                if ctx.max_installment_months and n > ctx.max_installment_months: continue
                first_pay = loader.pdate(o["first_payment_date"])
                freq = int(o["payment_frequency_days"])
                pmt_amt = loader.pfloat(o["payment_amount"])
                fin_fee = loader.pfloat(o["financing_fee"])
                payments = [(first_pay + timedelta(days=i*freq), pmt_amt) for i in range(n)]
                last = payments[-1][0]
                if last > deadline or last > horizon: continue
                if not pay_ok(payments): continue
                total = pmt_amt * n + fin_fee
                cands.append({"kind": "install", "method": "installments",
                              "status": "affordable_with_plan", "safe": safe,
                              "payments": payments, "cost": total, "changes": list(changes),
                              "complete": last, "start": first_pay, "opt": o["payment_option_id"],
                              "earliest": F.earliest_full_date(proj, rd, minb, A, 180)})
    return cands

def key_cand(c, req):
    dl = req.deadline or (req.rd + timedelta(days=90))
    return (0 if c["complete"] <= dl else 1, c["complete"], len(c["changes"]),
            round(c["cost"], 2), c["start"], len(c["payments"]), c["opt"])

def choose_spending_changes(ctx, req, opts):
    A = req.amount
    rd = req.rd
    ctx.var_daily_rate = var_daily_rate(ctx, rd)
    base_flows = F.build_flows(ctx, rd, [])
    base_proj = F.project(base_flows, ctx.balance, rd)
    safe = F.safe_amount(base_proj, rd, ctx.min_balance, A)
    if safe >= A - 1e-6:
        return [], build_candidates(ctx, req, opts, [])
    flex = []
    for it in ctx.monthlies:
        eid, cat = it["event_id"], it["cat"]
        if cat in ctx.protected: continue
        if it["flex"] == "stoppable" and cat in ctx.stop_cats:
            flex.append(("stop", eid, 0.0))
        if it["flex"] == "reducible" and cat in ctx.reduce_cats and it["min_allowed"] < it["amount"] - 1e-6:
            flex.append(("reduce", eid, it["min_allowed"]))
    combos = [[]]
    for f in flex:
        combos += [c + [f] for c in combos]
    combos = [c for c in combos if len(c) <= 3]
    best = None
    best_key = None
    best_changes = []
    for c in combos:
        for cand in build_candidates(ctx, req, opts, c):
            k = key_cand(cand, req)
            if best_key is None or k < best_key:
                best_key = k
                best = cand
                best_changes = c
    if best is None:
        return [], []
    return best_changes, [best]

def decide(ctx, req, opts):
    if not isinstance(req, Req): req = Req(req)
    A = req.amount
    rd = req.rd
    minb = ctx.min_balance
    deadline = req.deadline or (rd + timedelta(days=90))
    ctx.var_daily_rate = var_daily_rate(ctx, rd)
    flows = F.build_flows(ctx, rd, [])
    proj = F.project(flows, ctx.balance, rd)
    safe = F.safe_amount(proj, rd, minb, A)
    all_c = build_candidates(ctx, req, opts, [])
    changes, extra = choose_spending_changes(ctx, req, opts)
    all_c += extra
    if not all_c:
        return {"request_id": req.id, "amount_safe_to_pay": loader.fmt_amt(safe),
                "affordability_status": "not_affordable",
                "recommended_payment_method": "not_recommended", "payment_plan": "none",
                "earliest_date_for_full_payment": "",
                "spending_changes_needed": "none",
                "decision_explanation": explanation(ctx, req, None, safe, None)}
    best = min(all_c, key=lambda c: key_cand(c, req))
    return {"request_id": req.id, "amount_safe_to_pay": loader.fmt_amt(safe),
            "affordability_status": best["status"], "recommended_payment_method": best["method"],
            "payment_plan": "|".join("%s:%s" % (fmt_d(d), loader.fmt_amt(a)) for d, a in best["payments"]),
            "earliest_date_for_full_payment": fmt_d(best["earliest"]) if best.get("earliest") else "",
            "spending_changes_needed": "|".join(
                ("stop:%s" % e) if k == "stop" else ("reduce_to:%s:%s" % (e, loader.fmt_amt(a)))
                for k, e, a in best["changes"]) or "none",
            "decision_explanation": explanation(ctx, req, best, safe, best.get("earliest"))}

def explanation(ctx, req, best, safe, t):
    hm = ctx.home
    if best is None:
        return ("Requested %s %s cannot be paid within the forecast window without breaking the "
                "minimum balance of %s %s; safe amount today is %s %s." %
                (hm, loader.fmt_amt(req.amount), hm, loader.fmt_amt(ctx.min_balance),
                 hm, loader.fmt_amt(safe)))
    k = best["kind"]
    if k == "full":
        s = ("Balance comfortably covers the full %s %s on %s while keeping at least %s %s "
             "after all projected essentials." % (hm, loader.fmt_amt(req.amount), fmt_d(req.rd),
                                                  hm, loader.fmt_amt(ctx.min_balance)))
        if best["changes"]:
            s += " This requires spending changes: " + ", ".join(
                "stop %s" % e if kk == "stop" else "reduce %s to %s" % (e, loader.fmt_amt(aa))
                for kk, e, aa in best["changes"]) + "."
        return s
    if k == "wait":
        return ("Paying in full today would drop the balance below the required %s %s. The first "
                "safe full-payment date is %s, before the deadline of %s." %
                (hm, loader.fmt_amt(ctx.min_balance), fmt_d(best["complete"]),
                 fmt_d(req.deadline) if req.deadline else "the forecast horizon"))
    if k == "partial":
        return ("Only %s %s is safe today; the remaining %s %s can be paid on %s, completing "
                "before the deadline without touching the %s %s minimum." %
                (hm, loader.fmt_amt(best["payments"][0][1]), hm,
                 loader.fmt_amt(best["payments"][1][1]), fmt_d(best["complete"]),
                 hm, loader.fmt_amt(ctx.min_balance)))
    return ("Installment option %s (%s payments of %s %s starting %s) keeps the balance above "
            "%s %s and completes by %s, adding %s in financing cost." %
            (best["opt"], len(best["payments"]), hm, loader.fmt_amt(best["payments"][0][1]),
             fmt_d(best["start"]), hm, loader.fmt_amt(ctx.min_balance), fmt_d(best["complete"]),
             loader.fmt_amt(max(0.0, best["cost"] - req.amount))))
