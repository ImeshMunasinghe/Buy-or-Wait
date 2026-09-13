"""Data loading and per-user context building for Buy or Wait?"""
import csv
import os
import re
from datetime import date
from collections import defaultdict

from image_amounts import IMAGE_EVENT_AMOUNTS

CUR = r"(USD|EUR|IDR|INR|ZAR)"
AMT_RE = re.compile(CUR + r"\s*([\d][\d,\.]*)")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def pdate(s):
    s = (s or "").strip()[:10]
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def pfloat(s):
    try:
        return float((s or "0").replace(",", ""))
    except Exception:
        return 0.0


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fmt_amt(v):
    v = round(float(v) + 0.0, 2)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%0.2f" % v).rstrip("0").rstrip(".")


class Ctx:
    """Per-user financial context."""
    def __init__(self):
        self.home = "USD"
        self.balance = 0.0
        self.min_balance = 0.0
        self.methods = set()
        self.max_installment_months = None
        self.protected = set()
        self.reduce_cats = set()
        self.stop_cats = set()
        self.monthlies = []       # recurring monthly expense items
        self.salary_streams = []  # {day, amount}
        self.extra_credits = []   # confirmed one-off credits (date, amount)
        self.oneoff_debits = []   # pending/scheduled debits (date, amount, event_id)
        self.settled_debits = []  # variable settled debits (date, amount)
        self.var_daily_rate = 0.0


def _convert(amount, cur, home, on_date, rates_fwd):
    cur = (cur or "").strip().upper()
    if not cur or cur == home:
        return amount
    if (on_date, cur, home) in rates_fwd:
        return amount * rates_fwd[(on_date, cur, home)]
    if (on_date, home, cur) in rates_fwd and rates_fwd[(on_date, home, cur)]:
        return amount / rates_fwd[(on_date, home, cur)]
    return amount


def _parse_message(msg, mctx):
    """Message-derived amendments. mctx has salary_streams, extra_credits, settle_events,
    exclude_events, rent_multiplier."""
    text = msg.get("message_text", "") or ""
    low = text.lower()
    sent = pdate(msg.get("sent_at", "")[:10]) or date(1970, 1, 1)
    amounts = [pfloat(m.group(2).replace(",", "")) for m in AMT_RE.finditer(text)]
    dates = [d for d in (pdate(m.group(1)) for m in DATE_RE.finditer(text)) if d]
    src = msg.get("source_type", "")
    st = mctx["salary_streams"]

    if src == "employer":
        if "contract has ended" in low or ("kontrak" in low and "berakhir" in low):
            for s in st:
                s["stop_after"] = sent
            return
        if "berakhir" in low or "sisa gaji" in low or ("ended" in low and "remaining" in low):
            if amounts and st:
                for s in st:
                    s["amount"] = amounts[0]
                    s["stop_after"] = None
            return
        if "bonus" in low and ("not been approved" in low or "belum disetujui" in low or "menunggu" in low):
            return
        if amounts and any(k in low for k in ["reduced to", "monthly pay is", "naik menjadi", "gaji pokok",
                                              "salary is now", "regular salary of", "first salary",
                                              "salary will be", "salary of", "sisa gaji", "gaji rutin",
                                              "salary is reduced", "pay is"]):
            eff = dates[0] if dates else sent
            for s in st:
                s.setdefault("overrides", []).append((eff, amounts[0]))
        if "arrears" in low and amounts:
            eff = dates[0] if dates else sent
            mctx["extra_credits"].append((eff, amounts[-1]))
        return

    if src == "service_provider":
        if ("pembayaran faktur" in low or "invoice" in low and "approv" in low) and amounts:
            d = dates[0] if dates else sent
            mctx["extra_credits"].append((d, amounts[0]))
        if "rent" in low and "%" in low:
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
            if m:
                mctx["rent_multiplier"] = 1.0 + float(m.group(1)) / 100.0
                mctx["rent_effective"] = dates[0] if dates else sent
        return

    if src == "financial_service":
        if "reached your account" in low or "sudah masuk" in low or "settled in" in low:
            rel = msg.get("related_event_id", "").strip()
            if rel:
                mctx["settle_events"].add(rel)
        return

    if src == "bank":
        if "transfer between your two accounts" in low or "dua rekening" in low:
            rel = msg.get("related_event_id", "").strip()
            if rel:
                mctx["exclude_events"].add(rel)
        return
    # merchant: refund still processing -> ignore pending credits (no action)


VARIABLE_CATS = {"groceries", "transport", "dining", "shopping", "medical", "healthcare",
                  "entertainment", "personal_care", "clothing", "fuel", "miscellaneous",
                  "wellness", "fitness"}


def is_monthly_group(key, rows_):
    cat, desc = key
    if cat in VARIABLE_CATS:
        return False
    months = {(n["date"].year, n["date"].month) for n in rows_}
    return len(rows_) >= 3 and len(months) >= 3 and len(rows_) / len(months) <= 1.6


def load_dataset(dataset_dir):
    reqs = read_csv(os.path.join(dataset_dir, "requests.csv"))
    profiles = {r["user_id"]: r for r in read_csv(os.path.join(dataset_dir, "financial_profiles.csv"))}
    events = read_csv(os.path.join(dataset_dir, "financial_events.csv"))
    rates = read_csv(os.path.join(dataset_dir, "exchange_rates.csv"))
    options = read_csv(os.path.join(dataset_dir, "request_payment_options.csv"))
    messages = read_csv(os.path.join(dataset_dir, "messages.csv"))

    rates_fwd = {}
    for r in rates:
        d = pdate(r["rate_date"])
        rates_fwd[(d, r["from_currency"].strip(), r["to_currency"].strip())] = pfloat(r["rate"])

    ev_by_user = defaultdict(list)
    for e in events:
        ev_by_user[e["user_id"]].append(e)
    msg_by_user = defaultdict(list)
    for m in messages:
        msg_by_user[m["user_id"]].append(m)

    contexts = {}
    for uid, prof in profiles.items():
        ctx = Ctx()
        ctx.home = prof["home_currency"].strip()
        ctx.balance = pfloat(prof["current_available_balance"])
        ctx.min_balance = pfloat(prof["minimum_balance_to_keep"])
        ctx.methods = {m.strip() for m in prof["payment_methods_user_will_consider"].split("|") if m.strip()}
        mi = prof["max_installment_months"].strip()
        ctx.max_installment_months = int(mi) if mi else None
        ctx.protected = {c.strip() for c in prof["expense_categories_to_protect"].split("|") if c.strip()}
        ctx.reduce_cats = {c.strip() for c in prof["expense_categories_user_is_willing_to_reduce"].split("|") if c.strip()}
        ctx.stop_cats = {c.strip() for c in prof["expense_categories_user_is_willing_to_stop"].split("|") if c.strip()}

        mctx = {"salary_streams": ctx.salary_streams, "extra_credits": ctx.extra_credits,
                "settle_events": set(), "exclude_events": set(), "rent_multiplier": None}
        for msg in msg_by_user.get(uid, []):
            _parse_message(msg, mctx)

        rows = ev_by_user.get(uid, [])
        settle_ev = mctx["settle_events"]
        excl_ev = mctx["exclude_events"]

        norm = []
        for e in rows:
            eid = e["event_id"]
            if eid in excl_ev:
                continue
            status = e["status"].strip()
            if status in ("failed", "cancelled"):
                continue
            amt_s = e["amount"].strip()
            amt = IMAGE_EVENT_AMOUNTS[eid][0] if (amt_s == "" and eid in IMAGE_EVENT_AMOUNTS) else pfloat(amt_s)
            if amt == 0:
                continue
            d = pdate(e["settlement_date"]) or pdate(e["event_date"])
            if d is None:
                continue
            home_amt = _convert(amt, e["currency"], ctx.home, d, rates_fwd)
            norm.append({"id": eid, "type": e["event_type"].strip(), "cat": e["category"].strip(),
                         "desc": e["description"].strip(), "dir": e["direction"].strip(),
                         "amount": home_amt, "date": d, "status": status,
                         "flex": e["flexibility"].strip(), "min_allowed": pfloat(e["minimum_allowed_amount"]),
                         "linked": e["linked_event_id"].strip()})

        # reversed card-charge pairs net out: settled credit linked to an event
        linked_credits = {n["linked"] for n in norm
                          if n["dir"] == "credit" and n["status"] == "settled" and n["linked"]}
        if linked_credits:
            norm = [n for n in norm if n["id"] not in linked_credits
                    and n["linked"] not in linked_credits]

        settled = [n for n in norm if n["status"] == "settled"]
        pending = [n for n in norm if n["status"] in ("pending", "scheduled")]

        # salary streams: group settled income by day-of-month
        # stable income (salary) -> stream; variable income (commissions) -> one-off credits
        inc = [n for n in settled if n["dir"] == "credit" and n["type"] == "income"]
        byday = defaultdict(list)
        for n in inc:
            byday[n["date"].day].append(n)
        sal_descs = {"salary", "wage", "paycheck", "gaji", "payroll", "pay"}
        for day, rows_ in byday.items():
            amts = [n["amount"] for n in rows_]
            mu = sum(amts) / len(amts)
            desc = rows_[0]["desc"]
            stable = (max(amts) - min(amts)) / mu < 0.25 if mu > 0 else False
            is_sal = any(k in desc.lower() for k in sal_descs)
            if stable or is_sal:
                ctx.salary_streams.append({"day": day, "amount": mu,
                                           "desc": desc, "overrides": [],
                                           "stop_after": None})
            else:
                # variable income: use minimum as conservative recurring amount
                ctx.salary_streams.append({"day": day, "amount": min(amts),
                                           "desc": desc, "overrides": [],
                                           "stop_after": None})
        # Apply message-confirmed salary overrides to all streams
        for s in ctx.salary_streams:
            for eff, new_amt in sorted(s.get("overrides", [])):
                s["amount"] = new_amt
        # else treat as one-off credit
        sched_inc = [n for n in norm if n["dir"] == "credit" and n["type"] == "income"
                     and n["status"] in ("scheduled", "pending")]
        for n in sched_inc:
            matched = False
            for s in ctx.salary_streams:
                if s["day"] == n["date"].day:
                    s["amount"] = n["amount"]
                    matched = True
            if not matched:
                ctx.extra_credits.append((n["date"], n["amount"]))

        # recurring monthly expenses

        # recurring monthly expenses
        deb = [n for n in settled if n["dir"] == "debit"]
        groups = defaultdict(list)
        for n in deb:
            groups[(n["cat"], n["desc"])].append(n)
        monthly_keys = set()
        for key, rows_ in groups.items():
            if is_monthly_group(key, rows_):
                monthly_keys.add(key)
        for key, rows_ in groups.items():
            if key not in monthly_keys:
                continue
            rows_.sort(key=lambda n: n["date"])
            day = sorted(n["date"].day for n in rows_)[len(rows_) // 2]
            amts = [n["amount"] for n in rows_][-4:]
            last = rows_[-1]
            amount = sum(amts) / len(amts)
            if key[0] == "rent" and mctx.get("rent_multiplier"):
                amount *= mctx["rent_multiplier"]
            ctx.monthlies.append({"event_id": last["id"], "cat": key[0], "desc": key[1], "day": day,
                                  "amount": amount, "min_allowed": last["min_allowed"],
                                  "flex": last["flex"]})

        monthly_groups = monthly_keys
        var = [(n["date"], n["cat"], n["amount"]) for n in deb if (n["cat"], n["desc"]) not in monthly_groups]
        ctx.settled_debits = var

        for n in pending:
            if n["dir"] == "debit" and n["amount"] > 0:
                ctx.oneoff_debits.append((n["date"], n["amount"], n["id"]))
            elif n["dir"] == "credit" and n["id"] in settle_ev:
                ctx.extra_credits.append((n["date"], n["amount"]))
            elif n["dir"] == "credit" and n["type"] == "income":
                # confirmed salary counts on its settlement date
                ctx.extra_credits.append((n["date"], n["amount"]))

        contexts[uid] = ctx
    return reqs, contexts, options, profiles
