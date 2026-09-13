"""Temporary calibration experiment: find the forecast variant that best matches
the sample answers' earliest_date_for_full_payment values."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import loader, decide, forecast as F
from datetime import timedelta

DATASET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset")

FIXED_CATS = {"rent", "utilities", "debt_repayment", "education", "insurance",
              "loan_emi", "music_subscription", "delivery_membership", "cloud_storage",
              "streaming_subscription", "software_subscription", "internet_bill",
              "mobile_postpaid", "insurance_premium"}


def monthlies_for(ctx, mode):
    if mode == "perdesc":
        return ctx.monthlies
    if mode == "percat":
        agg = {}
        for m in ctx.monthlies:
            agg[m["cat"]] = agg.get(m["cat"], 0.0) + m["amount"]
        return [{"cat": c, "desc": c, "day": 1, "amount": a, "min_allowed": 0.0,
                 "flex": False, "event_id": "agg_" + c} for c, a in agg.items()]
    if mode == "fixed":
        agg = {}
        for m in ctx.monthlies:
            agg[m["cat"]] = agg.get(m["cat"], 0.0) + m["amount"]
        return [{"cat": c, "desc": c, "day": 1, "amount": a, "min_allowed": 0.0,
                 "flex": False, "event_id": "agg_" + c} for c, a in agg.items()
                if c in FIXED_CATS]
    if mode == "fixedperdesc":
        return [m for m in ctx.monthlies if m["cat"] in FIXED_CATS]
    return ctx.monthlies


def var_rate_for(ctx, window):
    if not ctx.settled_debits:
        return 0.0
    from datetime import date
    rd = ctx.var_ref
    first = date(rd.year, rd.month, 1)
    months = []
    for i in (1, 2, 3):
        mm = F.add_months(first, -i)
        months.append((mm.year, mm.month))
    total = sum(a for d, a in ctx.settled_debits if (d.year, d.month) in months)
    if total <= 0:
        return 0.0
    return total / (30.44 * 3)


def run_variant(month_mode, var_window, use_var):
    reqs, ctxs, opts, profs = loader.load_dataset(DATASET)
    srows = {r["request_id"]: r for r in loader.read_csv(os.path.join(DATASET, "sample_requests.csv"))}
    hits, tot, diffs = 0, 0, []
    for rid, row in srows.items():
        exp = (row.get("earliest_date_for_full_payment") or "").strip()
        if not exp:
            continue
        tot += 1
        ctx = ctxs[row["user_id"]]
        r = decide.Req(row)
        import copy; ctx2 = copy.copy(ctx)
        ctx2.monthlies = monthlies_for(ctx, month_mode)
        ctx2.settled_debits = ctx.settled_debits
        ctx2.var_ref = r.rd
        rate = var_rate_for(ctx2, var_window) if use_var else 0.0
        ctx2.var_daily_rate = rate
        pmin = F.project(F.build_flows(ctx2, r.rd, []), ctx2.balance, r.rd)
        t = F.earliest_full_date(pmin, r.rd, ctx2.min_balance, r.amount, 180)
        got = str(t) if t else ""
        if got == exp:
            hits += 1
        else:
            diffs.append("%s exp=%s got=%s" % (rid, exp, got or "never"))
    return hits, tot, diffs


if __name__ == "__main__":
    best = (0, None)
    for mm in ["perdesc", "percat", "fixed", "fixedperdesc"]:
        for uw, ww in [(True, 90), (True, 180), (True, 365), (False, 0)]:
            hits, tot, diffs = run_variant(mm, ww, uw)
            print("mode=%-14s var=%s/%-4s hits=%d/%d" % (mm, uw, ww, hits, tot))
            if hits > best[0]:
                best = (hits, diffs)
    print("\nBest diffs:")
    for d in best[1]:
        print("   ", d)
