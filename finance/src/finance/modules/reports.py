"""Reports over the ledger: payslips, statements, merchants, trends, recurring payments."""

from __future__ import annotations

import itertools
import statistics
from collections import defaultdict
from datetime import timedelta

from .. import (
    audit,
    categorize,
    clock,
    dates,
    db,
    planning,
    verify,
)
from ..db import rows


def currencies(conn, a=None):
    """The currencies in your ledger with how many payments each has, and which one is being viewed. Totals never mix them."""

    main = db.get_setting(conn, "currency", "EUR")
    out = rows(
        conn.execute("SELECT COALESCE(NULLIF(currency,''), ?) AS currency, COUNT(*) AS payments FROM transactions GROUP BY 1 ORDER BY payments DESC", (main,))
    )
    viewing = db.view_currency(conn)
    return {"viewing": viewing, "main": main, "currencies": out}


def agent_list(conn, a=None):
    """Every verifier and helper agent, grouped, with whether it is running today or only planned."""
    return {
        "agents": verify.AGENTS,
        "built": sum(1 for x in verify.AGENTS if x["status"] == "built"),
        "planned": sum(1 for x in verify.AGENTS if x["status"] == "planned"),
    }


def verification_report(conn, a=None):
    """What every verifier agent concluded: counts per agent, and every warning and failure in words."""
    found = rows(conn.execute("SELECT agent, level, subject, message FROM findings ORDER BY (level='fail') DESC, (level='warn') DESC, agent, subject"))
    summary: dict[str, dict[str, int]] = {}
    for f in found:
        summary.setdefault(f["agent"], {"ok": 0, "warn": 0, "fail": 0})[f["level"]] += 1
    return {"summary": summary, "problems": [f for f in found if f["level"] != "ok"], "passed": sum(1 for f in found if f["level"] == "ok")}


def list_payslips(conn, a=None):
    """Payslips by month: gross, tax, pension, holiday pay and net, in currency units."""
    out = rows(
        conn.execute(
            "SELECT period, name, gross_minor/100.0 AS gross, tax_minor/100.0 AS tax, pension_minor/100.0 AS pension, "
            "holiday_minor/100.0 AS holiday, net_minor/100.0 AS net FROM payslips ORDER BY period DESC, name"
        )
    )
    return out[: int((a or {}).get("limit", 36))]


def files_to_check(conn, a=None):
    """Statements that could not be proven correct (not imported) or could not be checked (imported, marked), with the reason."""
    return rows(conn.execute("SELECT name AS file, status, issues FROM statement_files WHERE status IN ('needs_check','unverified') ORDER BY status, name"))


def weekly_summary(conn, a=None):
    """What changed in the last days, what is due next, and what needs a check. Every figure is read from the books; nothing is estimated."""
    days = max(1, min(int((a or {}).get("days", 7)), 31))
    since = (clock.today() - timedelta(days=days)).isoformat()
    added = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN kind='expense' THEN amount_minor END),0) AS spent, "
        "COALESCE(SUM(CASE WHEN kind='income' THEN amount_minor END),0) AS income FROM transactions WHERE substr(created,1,10)>=?",
        (since,),
    ).fetchone()
    files = rows(conn.execute("SELECT name, status FROM statement_files WHERE substr(at,1,10)>=? ORDER BY at DESC LIMIT 20", (since,)))
    due = planning.bills_due(conn, {"days": 14})
    check = rows(conn.execute("SELECT name AS file, status, issues FROM statement_files WHERE status IN ('needs_check','unverified') ORDER BY name LIMIT 20"))
    problems = [p for p in verification_report(conn)["problems"] if p["level"] == "fail"][:10]
    return {
        "since": since,
        "changed": {"new_payments": added["n"], "spent": added["spent"] / 100, "income": added["income"] / 100, "files_read": files},
        "due_next_14_days": due,
        "needs_a_check": {"files": check, "failed_checks": problems},
    }


def statement_report(conn, a=None):
    """For each finance file: what Finance made of it, with no content shown. Use it to see which files could not be read."""
    out = []
    for d in conn.execute(
        "SELECT d.name, d.kind, d.text, s.found, s.added FROM documents d LEFT JOIN statement_files s ON s.sha256=d.sha256 "
        "WHERE d.area='finance' ORDER BY d.name"
    ):
        slip = bool(conn.execute("SELECT 1 FROM payslips WHERE name=?", (d["name"],)).fetchone())
        out.append(
            {
                "file": d["name"],
                "type": d["kind"],
                "text_characters": len(d["text"]),
                "payslip": slip,
                "transactions_found": d["found"],
                "imported": d["added"],
                "read": d["found"] is not None,
            }
        )
    return out


def _range(a):
    where, args = ["kind='expense'", "category<>'transfers'"], []
    if a.get("month"):
        start, end = dates.month_bounds(a["month"])
        where += ["day>=?", "day<?"]
        args += [start, end]
    for col, op, key in (("day", ">=", "since"), ("day", "<=", "until")):
        if a.get(key):
            where.append(f"{col} {op} ?")
            args.append(a[key])
    return " AND ".join(where), args


def top_merchants(conn, a):
    """Where the money went: spend grouped by merchant, biggest first."""
    where, args = _range(a)
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for r in conn.execute(f"SELECT note, amount_minor FROM ledger WHERE {where}", args):
        m = categorize.merchant(r["note"]) or "(unnamed)"
        totals[m][0] += r["amount_minor"] / 100
        totals[m][1] += 1
    ranked = sorted(totals.items(), key=lambda kv: -kv[1][0])[: int(a.get("limit", 15))]
    return [{"merchant": m, "spent": round(t, 2), "times": n} for m, (t, n) in ranked]


def monthly_trend(conn, a):
    months = max(1, min(int(a.get("months", 6)), 60))
    out = rows(
        conn.execute(
            "SELECT substr(day,1,7) AS month, SUM(CASE WHEN kind='expense' THEN amount_minor ELSE 0 END)/100.0 AS spent, "
            "SUM(CASE WHEN kind='income' THEN amount_minor ELSE 0 END)/100.0 AS income FROM ledger "
            "WHERE category<>'transfers' GROUP BY month ORDER BY month DESC LIMIT ?",
            (months,),
        )
    )
    for r in out:
        r["net"] = round(r["income"] - r["spent"], 2)
    return list(reversed(out))


def recurring_payments(conn, a=None):
    """Payments that repeat about monthly for about the same amount: subscriptions, rent, EMIs, bills."""
    by: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for r in conn.execute("SELECT day, note, amount_minor FROM ledger WHERE kind='expense' AND category<>'transfers' ORDER BY day"):
        m = categorize.merchant(r["note"])
        if m:
            by[m].append((r["day"], r["amount_minor"]))
    found = []
    for m, items in by.items():
        if len(items) < 3:
            continue
        days = [dates.parse(d) for d, _ in items]
        gaps = [(b - a_).days for a_, b in itertools.pairwise(days) if (b - a_).days > 0]
        amounts = [x for _, x in items]
        mid = statistics.median(amounts)
        if gaps and 25 <= statistics.median(gaps) <= 35 and sum(abs(x - mid) <= 0.15 * mid for x in amounts) >= 0.7 * len(amounts):
            found.append({"merchant": m, "typical_amount": round(mid / 100, 2), "times": len(items), "last": items[-1][0], "per_month": round(mid / 100, 2)})
    return sorted(found, key=lambda x: -x["typical_amount"])


def uncategorised(conn, a=None):
    """The merchants still in 'other', biggest first, so a few corrections place most of the rest."""
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for r in conn.execute("SELECT note, amount_minor FROM ledger WHERE category='other'"):
        m = categorize.merchant(r["note"])
        if m:
            totals[m][0] += r["amount_minor"] / 100
            totals[m][1] += 1
    return [{"merchant": m, "spent": round(t, 2), "times": n} for m, (t, n) in sorted(totals.items(), key=lambda kv: -kv[1][0])[:25]]


def set_category(conn, a):
    """Put every transaction from a merchant into a category, now and in future imports."""
    m = categorize.teach(conn, a["merchant"], a["category"])
    audit.record(conn, "category set", f"{m} -> {a['category']}")
    return {"merchant": m, "category": a["category"].lower()}
