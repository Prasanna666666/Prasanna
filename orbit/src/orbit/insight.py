"""The insight agents: they watch your payments and documents and speak up only when something deserves a look. Exact arithmetic and plain rules; no model.

Merchant normaliser · duplicate payments · price changes · unusual payments · refund matcher · forecast · net worth
Tax letters · insurance and contracts · year-end · VAT · exchange-rate freshness · scan quality · audit chain · self-test · backup
"""

from __future__ import annotations

import difflib
import json
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta

from . import audit, backup, canary, categorize, rates, tables
from .db import get_setting
from .verify import Finding


def _main(conn) -> str:
    return get_setting(conn, "currency", "EUR")


def _aliases(conn) -> dict[str, str]:
    return {r["alias"]: r["canonical"] for r in conn.execute("SELECT alias, canonical FROM merchant_alias")}


def _name(conn_aliases: dict[str, str], note: str) -> str:
    m = categorize.merchant(note)
    return conn_aliases.get(m, m)


def _d(day: str) -> date:
    return date.fromisoformat(day)


def _money(minor: int) -> str:
    return f"{minor / 100:,.2f}"


# ---- merchant normaliser -----------------------------------------------------------------------------------------------------
def merchant_aliases(conn) -> list[Finding]:
    """'albert heijn' and 'albert heijn utrecht 1234' are one shop: the more common name wins and the other becomes its alias."""
    counts: dict[str, int] = defaultdict(int)
    for r in conn.execute("SELECT note FROM transactions"):
        m = categorize.merchant(r["note"])
        if m:
            counts[m] += 1
    canon: list[str] = []
    mapping: dict[str, str] = {}
    for name in sorted(counts, key=lambda n: (-counts[n], len(n), n)):
        toks = set(name.split())
        match = None
        for c in canon:
            ct = set(c.split())
            small, big = (toks, ct) if len(toks) <= len(ct) else (ct, toks)
            subset = small <= big and (len(small) >= 2 or (small and max(len(t) for t in small) >= 5))
            if subset or difflib.SequenceMatcher(None, name, c).ratio() >= 0.9:
                match = c
                break
        if match:
            mapping[name] = match
        else:
            canon.append(name)
    conn.execute("DELETE FROM merchant_alias")
    conn.executemany("INSERT INTO merchant_alias (alias, canonical) VALUES (?,?)", list(mapping.items()))
    conn.commit()
    return [Finding("merchant names", "ok", "shops", f"{len(mapping)} spelling variant(s) of the same shop are treated as one")] if mapping else []


# ---- regular payments: forecast and price changes ----------------------------------------------------------------------------
def _recurring(conn) -> list[dict]:
    main, al = _main(conn), _aliases(conn)
    by: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for r in conn.execute("SELECT day, note, amount_minor, COALESCE(NULLIF(currency,''), ?) AS cur FROM transactions WHERE kind='expense' AND category<>'transfers' "
                          "AND event_id IS NULL AND source<>'derived' ORDER BY day", (main,)):
        m = _name(al, r["note"])
        if m:
            by[(r["cur"], m)].append((r["day"], r["amount_minor"]))
    out = []
    for (cur, m), items in by.items():
        if len(items) < 3:
            continue
        days = [_d(d) for d, _ in items]
        gaps = [(b - a).days for a, b in zip(days, days[1:], strict=False) if (b - a).days > 0]
        amounts = [x for _, x in items]
        mid = statistics.median(amounts)
        if gaps and 25 <= statistics.median(gaps) <= 35 and sum(abs(x - mid) <= 0.15 * mid for x in amounts) >= 0.7 * len(amounts):
            out.append({"cur": cur, "merchant": m, "items": items, "gap": round(statistics.median(gaps))})
    return out


def price_changes(conn) -> list[Finding]:
    out = []
    for g in _recurring(conn):
        amounts = [a for _, a in g["items"]]
        before = statistics.median(amounts[-4:-1])
        last = amounts[-1]
        if before and abs(last - before) / before > 0.03 and abs(last - before) >= 5:
            pct = (last - before) / before * 100
            out.append(Finding("price changes", "warn", g["merchant"], f"{g['merchant']} went from {_money(round(before))} to {_money(last)} {g['cur']} ({pct:+.0f}%) on {g['items'][-1][0]}"))
    return out or [Finding("price changes", "ok", "regular payments", "no regular payment changed its price")] if _recurring_exists(conn) else out


def _recurring_exists(conn) -> bool:
    return bool(_recurring(conn))


def upcoming_payments(conn, a=None):
    """The regular payments due soon: each repeating payment's last date plus its usual gap, with its usual amount."""
    a = a or {}
    today = _d(a["today"]) if a.get("today") else date.today()
    horizon = int(a.get("days", 35))
    out = []
    for g in _recurring(conn):
        last_day, _ = g["items"][-1]
        due = _d(last_day) + timedelta(days=g["gap"])
        if today - timedelta(days=3) <= due <= today + timedelta(days=horizon):
            amount = statistics.median([x for _, x in g["items"][-3:]])
            out.append({"merchant": g["merchant"], "amount": round(amount) / 100, "currency": g["cur"], "due": due.isoformat(), "in_days": (due - today).days})
    return sorted(out, key=lambda x: x["due"])[:10]


# ---- watching for trouble ----------------------------------------------------------------------------------------------------
def duplicate_payments(conn) -> list[Finding]:
    """The same shop, the same amount, the same account, within two days: possibly charged twice."""
    main, al = _main(conn), _aliases(conn)
    out, last = [], None
    # sorted so that equal payments sit next to each other: one pass, no pairwise comparison
    for r in conn.execute("SELECT day, amount_minor, note, account, COALESCE(NULLIF(currency,''), ?) AS cur FROM transactions WHERE kind='expense' AND amount_minor>=500 "
                          "AND category<>'transfers' AND transfer_id IS NULL AND event_id IS NULL ORDER BY account, cur, amount_minor, day", (main,)):
        name = _name(al, r["note"])
        if last and name and last["name"] == name and last["key"] == (r["account"], r["cur"], r["amount_minor"]) and 0 <= (_d(r["day"]) - _d(last["day"])).days <= 2:
            out.append((r["day"], Finding("duplicate payments", "warn", name, f"{name}: {_money(r['amount_minor'])} {r['cur']} on {last['day']}" +
                                          (f" and again on {r['day']}" if r["day"] != last["day"] else " twice the same day") + ": charged twice?")))
        last = {"name": name, "key": (r["account"], r["cur"], r["amount_minor"]), "day": r["day"]}
    return [f for _, f in sorted(out, key=lambda x: x[0], reverse=True)[:10]]


def unusual_payments(conn, today: date | None = None) -> list[Finding]:
    """A recent payment far above what that shop usually costs you."""
    today = today or date.today()
    main, al = _main(conn), _aliases(conn)
    by: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for r in conn.execute("SELECT day, note, amount_minor, COALESCE(NULLIF(currency,''), ?) AS cur FROM transactions WHERE kind='expense' AND category<>'transfers' AND event_id IS NULL "
                          "AND source<>'derived'", (main,)):
        m = _name(al, r["note"])
        if m:
            by[(r["cur"], m)].append((r["day"], r["amount_minor"]))
    out = []
    for (cur, m), items in by.items():
        if len(items) < 6:
            continue
        vals = [a for _, a in items]
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals])
        for day, amt in items:
            if (today - _d(day)).days <= 60 and amt > med + 5 * max(mad, 0.05 * med) and amt >= 1.5 * med and amt >= 2500:
                out.append(Finding("unusual payments", "warn", m, f"{m}: {_money(amt)} {cur} on {day} is much more than the usual {_money(round(med))}"))
    return out[:8]


def refund_matcher(conn) -> list[Finding]:
    """Ties each refund to the purchase it gives money back for: same shop, not more than was paid, within the 90 days before."""
    main, al = _main(conn), _aliases(conn)
    matched = lone = 0
    for r in conn.execute("SELECT id, day, note, amount_minor, category, account, COALESCE(NULLIF(currency,''), ?) AS cur FROM transactions WHERE kind='income' AND refund_of IS NULL "
                          "AND event_id IS NULL AND category NOT IN ('salary','interest','transfers') AND source<>'derived'", (main,)).fetchall():
        m = _name(al, r["note"])
        best = None
        for p in conn.execute("SELECT id, day, note, amount_minor FROM transactions WHERE kind='expense' AND amount_minor>=? AND day<=? AND day>=? AND account=? "
                              "AND COALESCE(NULLIF(currency,''), ?)=? ORDER BY day DESC", (r["amount_minor"], r["day"], (_d(r["day"]) - timedelta(days=90)).isoformat(), r["account"], main, r["cur"])):
            if m and _name(al, p["note"]) == m:
                best = p
                break
        if best:
            conn.execute("UPDATE transactions SET refund_of=? WHERE id=?", (best["id"], r["id"]))
            matched += 1
        elif r["category"] == "refund":
            lone += 1
    conn.commit()
    out = []
    total = conn.execute("SELECT COUNT(*) FROM transactions WHERE refund_of IS NOT NULL").fetchone()[0]
    if total:
        out.append(Finding("refunds", "ok", "refunds", f"{total} refund(s) tied to the purchase they belong to"))
    if lone:
        out.append(Finding("refunds", "warn", "refunds", f"{lone} refund(s) have no matching purchase in the 90 days before"))
    return out


# ---- net worth ---------------------------------------------------------------------------------------------------------------
def net_worth(conn, a=None):
    """The balance of every account in euros, month by month, from the closing balances of your proven statements."""
    main = _main(conn)
    files = list(conn.execute("SELECT account, currency, period_end, closing_minor FROM statement_files WHERE status='verified' AND closing_minor IS NOT NULL AND period_end IS NOT NULL AND account<>'' ORDER BY period_end"))
    if not files:
        return {"latest": None, "series": [], "accounts": [], "missing_rates": 0}

    def eur(account_cur: str, minor: int, day: str):
        if account_cur == "EUR":
            return minor
        found = rates.rate_on(conn, account_cur, day)
        return rates.to_eur(minor, found[0]) if found else None

    by_acc: dict[str, list] = defaultdict(list)
    for f in files:
        by_acc[f["account"]].append((f["period_end"], f["closing_minor"], f["currency"] or main))
    months = sorted({d[:7] for v in by_acc.values() for d, _, _ in v})
    end = date.fromisoformat(months[-1] + "-28")
    series, missing = [], 0
    cur_month = date.fromisoformat(months[0] + "-01")
    while cur_month <= end:
        total, complete = 0, True
        limit = (date(cur_month.year + (cur_month.month == 12), cur_month.month % 12 + 1, 1) - timedelta(days=1)).isoformat()
        for acc, items in by_acc.items():
            upto = [i for i in items if i[0] <= limit]
            if upto:
                day, minor, c = upto[-1]
                v = eur(c, minor, day)
                if v is None:
                    complete = False
                else:
                    total += v
        if complete:
            series.append({"month": cur_month.strftime("%Y-%m"), "eur": total / 100})
        else:
            missing += 1
        cur_month = (cur_month.replace(day=28) + timedelta(days=5)).replace(day=1)
    accounts = []
    for acc, items in by_acc.items():
        day, minor, c = items[-1]
        v = eur(c, minor, day)
        accounts.append({"account": acc, "currency": c, "balance": minor / 100, "eur": None if v is None else v / 100, "as_of": day})
    return {"latest": series[-1]["eur"] if series else None, "series": series, "accounts": accounts, "missing_rates": missing}


# ---- documents against each other --------------------------------------------------------------------------------------------
def _covered(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT substr(day,1,7) FROM transactions")}


def tax_letters(conn) -> list[Finding]:
    """A tax letter's amount should appear as a payment (or a refund received) within about three months of its date."""
    out, covered = [], _covered(conn)
    for d in conn.execute("SELECT name, party, doc_date, total_minor FROM finance_docs WHERE kind='tax' AND total_minor IS NOT NULL AND doc_date IS NOT NULL"):
        lo, hi = (_d(d["doc_date"]) - timedelta(days=5)).isoformat(), (_d(d["doc_date"]) + timedelta(days=90)).isoformat()
        hit = conn.execute("SELECT kind, day FROM transactions WHERE amount_minor=? AND day>=? AND day<=? LIMIT 1", (d["total_minor"], lo, hi)).fetchone()
        label = f"tax letter {d['party'] or d['name']}"
        if hit:
            out.append(Finding("tax letters", "ok", d["name"], f"{label}: {_money(d['total_minor'])} {'received' if hit['kind'] == 'income' else 'paid'} on {hit['day']}"))
        elif d["doc_date"][:7] in covered:
            out.append(Finding("tax letters", "warn", d["name"], f"{label}: no payment or refund of {_money(d['total_minor'])} found"))
    return out


def insurance_contracts(conn) -> list[Finding]:
    """An insurance premium or contract amount should appear as payments (the amount, or a twelfth of it, within 1%)."""
    out, covered = [], _covered(conn)
    for d in conn.execute("SELECT name, kind, party, doc_date, total_minor FROM finance_docs WHERE kind IN ('insurance','contract') AND total_minor IS NOT NULL AND doc_date IS NOT NULL"):
        t = d["total_minor"]
        hit = conn.execute("SELECT COUNT(*) FROM transactions WHERE kind='expense' AND day>=? AND (abs(amount_minor-?)<=? OR abs(amount_minor-?)<=?)",
                           ((_d(d["doc_date"]) - timedelta(days=35)).isoformat(), t, max(1, t // 100), t // 12, max(1, t // 1200))).fetchone()[0]
        label = f"{d['kind']} {d['party'] or d['name']}"
        if hit:
            out.append(Finding("insurance and contracts", "ok", d["name"], f"{label}: {hit} payment(s) match {_money(t)} or a twelfth of it"))
        elif d["doc_date"][:7] in covered:
            out.append(Finding("insurance and contracts", "warn", d["name"], f"{label}: no payment of about {_money(t)} found"))
    return out


def year_end(conn) -> list[Finding]:
    """Your annual income statement must match the sum of that year's payslips: gross, tax and net."""
    out = []
    for d in conn.execute("SELECT name, period, gross_minor, tax_minor, net_minor FROM finance_docs WHERE kind='annual_statement' AND period<>''"):
        year = d["period"][:4]
        slips = list(conn.execute("SELECT gross_minor, tax_minor, net_minor FROM payslips WHERE period LIKE ?", (f"{year}-%",)))
        if not slips:
            out.append(Finding("year-end", "warn", d["name"], f"annual statement {year}: no payslips for that year to compare with"))
            continue
        problems = []
        for label, key in (("gross", "gross_minor"), ("tax", "tax_minor"), ("net", "net_minor")):
            if d[key] is None:
                continue
            added = sum((s[key] or 0) for s in slips)
            if added != d[key]:
                problems.append(f"{label}: statement {_money(d[key])}, payslips {_money(added)}")
        out.append(Finding("year-end", "fail", d["name"], f"annual statement {year} and its {len(slips)} payslip(s) disagree: " + "; ".join(problems)) if problems else
                   Finding("year-end", "ok", d["name"], f"annual statement {year} matches its {len(slips)} payslip(s)" + ("" if len(slips) == 12 else f" (only {len(slips)} of 12 months)")))
    return out


def vat_agent(conn) -> list[Finding]:
    """VAT on invoices and receipts must be less than the total; the VAT per year is added up for you."""
    out = []
    bad = conn.execute("SELECT name FROM finance_docs WHERE kind IN ('invoice','receipt') AND vat_minor IS NOT NULL AND total_minor IS NOT NULL AND vat_minor>total_minor").fetchall()
    for b in bad:
        out.append(Finding("VAT", "fail", b["name"], "the VAT is larger than the total"))
    for r in conn.execute("SELECT substr(doc_date,1,4) AS year, COUNT(*) AS n, SUM(vat_minor) AS vat FROM finance_docs WHERE kind IN ('invoice','receipt') AND vat_minor IS NOT NULL AND doc_date IS NOT NULL GROUP BY 1"):
        out.append(Finding("VAT", "ok", r["year"], f"VAT in {r['year']}: {_money(r['vat'])} on {r['n']} document(s)"))
    return out


# ---- the machinery itself ----------------------------------------------------------------------------------------------------
def rate_freshness(conn) -> list[Finding]:
    main = _main(conn)
    foreign = conn.execute("SELECT COUNT(*), MAX(day) FROM transactions WHERE COALESCE(NULLIF(currency,''), ?) <> 'EUR'", (main,)).fetchone()
    if not foreign[0]:
        return []
    newest = conn.execute("SELECT MAX(day) FROM rates").fetchone()[0]
    if not newest:
        return [Finding("exchange rates", "warn", "rates", "there are payments in other currencies but no exchange rates are loaded (run ./scripts/fetch-rates.sh)")]
    if (_d(foreign[1]) - _d(newest)).days > 7:
        return [Finding("exchange rates", "warn", "rates", f"the exchange rates end on {newest}, but payments go up to {foreign[1]}: refresh them (./scripts/fetch-rates.sh)")]
    return [Finding("exchange rates", "ok", "rates", f"exchange rates are loaded up to {newest}")]


def scan_quality(conn) -> list[Finding]:
    """Scanned pages are read by OCR: say how well, and flag any figure the two reading passes disagreed on."""
    out, pages, weak = [], 0, []
    for d in conn.execute("SELECT name, data FROM documents"):
        try:
            meta = (json.loads(d["data"]) if d["data"] else {}).get("meta") or {}
        except ValueError:
            continue
        if meta.get("ocr_pages"):
            pages += meta["ocr_pages"]
            if meta.get("ocr_confidence", 100) < 85:
                weak.append((d["name"], meta["ocr_confidence"]))
            if meta.get("ocr_disagreements"):
                out.append(Finding("scan quality", "warn", d["name"], f"two readings of this scan disagree on {meta['ocr_disagreements']} figure(s): check it"))
    for name, conf in weak:
        out.append(Finding("scan quality", "warn", name, f"this scan was hard to read ({conf:.0f}% sure)"))
    if pages and not out:
        out.append(Finding("scan quality", "ok", "scans", f"{pages} scanned page(s) were read clearly, and both readings agree"))
    return out


def audit_chain(conn) -> list[Finding]:
    ok, n, why = audit.verify_chain(conn)
    return [Finding("audit log", "ok" if ok else "fail", "log", f"the record of imports and changes is intact ({n} entries)" if ok else f"the record of imports and changes has been tampered with: {why}")] if n or not ok else []


def self_test(conn) -> list[Finding]:
    return canary.run()


def backup_status(conn) -> list[Finding]:
    return backup.daily(conn)


EXTRA_AGENTS = (merchant_aliases, price_changes, duplicate_payments, unusual_payments, refund_matcher, tax_letters, insurance_contracts, year_end, vat_agent,
                rate_freshness, scan_quality, audit_chain, self_test, backup_status)
_ = tables  # imported for completeness of the agent toolkit
