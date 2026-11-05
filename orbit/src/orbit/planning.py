"""The planning side of Orbit: years, savings, goals, forecast, timeline, interest, investments, insurance and things worth a look.

Every number here is computed from the same proven ledger as the rest of the app, by exact arithmetic. Nothing is invented: a forecast is a labelled estimate
from your own recent months, a suggestion is a rule applied to your figures (and says which), and anything that needs data Orbit does not have (the value of an
investment portfolio, for example) says so instead of guessing."""

from __future__ import annotations

import itertools
import re
import statistics
from collections import defaultdict
from datetime import date
from typing import Any

from . import clock, insight, proof
from .db import get_setting


def _currency(conn) -> str:
    return get_setting(conn, "view_currency", "") or get_setting(conn, "currency", "EUR")


def _months(conn) -> list[dict]:
    """Every month with data: money in, money spent, in currency units, from the ledger (transfers between your own accounts left out)."""
    return [
        {"month": r["m"], "income": r["i"] / 100, "spent": r["s"] / 100}
        for r in conn.execute(
            "SELECT substr(day,1,7) AS m, SUM(CASE WHEN kind='income' AND NOT (event_id IS NOT NULL) THEN amount_minor ELSE 0 END) AS i, "
            "SUM(CASE WHEN kind='expense' THEN amount_minor ELSE 0 END) AS s FROM ledger WHERE category<>'transfers' GROUP BY m ORDER BY m"
        )
    ]


# ---- years: income, expenses, savings, savings rate, interest ---------------------------------------------------------------------
def yearly_overview(conn, a=None):
    """Per year: salary, money in, spent, saved, savings rate, interest earned, invested, insurance paid, and how many months the year is made of."""
    out: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT substr(day,1,4) AS y, kind, category, SUM(amount_minor) AS t, COUNT(DISTINCT substr(day,1,7)) AS months FROM ledger "
        "WHERE category<>'transfers' AND NOT (kind='income' AND event_id IS NOT NULL) GROUP BY y, kind, category"
    ):
        y = out.setdefault(
            r["y"], {"year": r["y"], "salary": 0.0, "income": 0.0, "spent": 0.0, "interest": 0.0, "invested": 0.0, "insurance": 0.0, "months": 0}
        )
        amount = r["t"] / 100
        y["months"] = max(y["months"], r["months"])
        if r["kind"] == "income":
            y["income"] += amount
            if r["category"] == "salary":
                y["salary"] += amount
            if r["category"] == "interest":
                y["interest"] += amount
        else:
            y["spent"] += amount
            if r["category"] == "investments":
                y["invested"] += amount
            if r["category"] == "insurance":
                y["insurance"] += amount
    result = []
    for y in sorted(out.values(), key=lambda x: x["year"]):
        saved = y["income"] - y["spent"]
        y.update(saved=round(saved, 2), savings_rate=round(saved / y["income"] * 100, 1) if y["income"] > 0 else None)
        result.append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in y.items()})
    return {"currency": _currency(conn), "years": result}


# ---- interest ----------------------------------------------------------------------------------------------------------------------
def interest(conn, a=None):
    """Interest received per year, and an ESTIMATED yearly rate for each account that earns it. The rate uses only the interest earned inside the statement periods that
    are loaded, divided by the average of those statements' closing balances, scaled to a full year by the days those statements cover."""
    out = []
    for r in conn.execute(
        "SELECT substr(day,1,4) AS y, account, SUM(amount_minor) AS t FROM ledger WHERE kind='income' AND category='interest' GROUP BY y, account"
    ).fetchall():
        files = conn.execute(
            "SELECT period_start, period_end, closing_minor FROM statement_files WHERE account=? AND substr(period_end,1,4)=? AND period_start IS NOT NULL AND closing_minor IS NOT NULL AND status='verified'",
            (r["account"], r["y"]),
        ).fetchall()
        rate = average = None
        if files:
            days = sum((date.fromisoformat(f["period_end"]) - date.fromisoformat(f["period_start"])).days + 1 for f in files)
            average = statistics.mean(f["closing_minor"] for f in files)
            earned = sum(
                x["amount_minor"]
                for f in files
                for x in conn.execute(
                    "SELECT amount_minor FROM ledger WHERE kind='income' AND category='interest' AND account=? AND day>=? AND day<=?",
                    (r["account"], f["period_start"], f["period_end"]),
                )
            )
            if average > 0 and days > 0:
                rate = round(earned / average * 365 / days * 100, 2)
        out.append(
            {
                "year": r["y"],
                "account": (r["account"] or "")[-4:],
                "interest": r["t"] / 100,
                "average_balance": None if average is None else round(average / 100, 2),
                "rate_percent": rate,
                "note": "estimate: interest earned in the loaded statement periods, scaled to a year"
                if rate is not None
                else "no proven statement balance to compare with",
            }
        )
    return {"currency": _currency(conn), "by_year": sorted(out, key=lambda x: (x["year"], x["account"]))}


# ---- investments and insurance -----------------------------------------------------------------------------------------------------
def investments(conn, a=None):
    """What went into investments each year (payments to brokers, funds and pension schemes), and the honest limit: the VALUE of a portfolio needs your broker's statements."""
    per_year = [
        {"year": r["y"], "contributed": r["t"] / 100, "payments": r["n"]}
        for r in conn.execute(
            "SELECT substr(day,1,4) AS y, SUM(amount_minor) AS t, COUNT(*) AS n FROM ledger WHERE kind='expense' AND category='investments' GROUP BY y ORDER BY y"
        )
    ]
    returned = conn.execute("SELECT SUM(amount_minor) FROM ledger WHERE kind='income' AND category='investments'").fetchone()[0] or 0
    holdings = conn.execute("SELECT COUNT(*) FROM finance_docs WHERE kind IN ('portfolio','broker_statement')").fetchone()[0]
    return {
        "currency": _currency(conn),
        "contributed_by_year": per_year,
        "paid_out_to_you": returned / 100,
        "portfolio_value": None,
        "note": "Orbit knows what you paid in, not what it is worth now: that needs your broker's holdings statement, which it cannot read yet."
        if not holdings
        else "",
    }


def insurances(conn, a=None):
    """Each insurance: what the documents say it costs, and what was actually paid per year."""
    docs = [
        dict(r)
        for r in conn.execute("SELECT name, party, doc_date, total_minor/100.0 AS amount FROM finance_docs WHERE kind='insurance' ORDER BY doc_date DESC")
    ]
    paid: dict[tuple[str, str], float] = defaultdict(float)
    for r in conn.execute("SELECT substr(day,1,4) AS y, note, amount_minor FROM ledger WHERE kind='expense' AND category='insurance'"):
        paid[(r["y"], insight._name(insight._aliases(conn), r["note"]) or "(unnamed)")] += r["amount_minor"] / 100
    return {
        "currency": _currency(conn),
        "documents": docs,
        "paid": [{"year": y, "insurer": n, "paid": round(v, 2)} for (y, n), v in sorted(paid.items())],
        "total_per_year": [{"year": y, "paid": round(sum(v for (yy, _), v in paid.items() if yy == y), 2)} for y in sorted({k[0] for k in paid})],
    }


# ---- goals ------------------------------------------------------------------------------------------------------------------------
def add_goal(conn, a):
    name = str(a.get("name", "")).strip()
    amount = round(float(a["target"]) * 100)
    if not name or amount <= 0:
        raise ValueError("a goal needs a name and a positive target")
    by = a.get("by")
    if by:
        date.fromisoformat(str(by))
    cur = conn.execute("INSERT INTO goals (name, target_minor, by_date) VALUES (?,?,?)", (name[:80], amount, by))
    conn.commit()
    return {"id": cur.lastrowid, "name": name, "target": amount / 100, "by": by}


def delete_goal(conn, a):
    conn.execute("DELETE FROM goals WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


def _saved_now(conn) -> float | None:
    """What you have now: the total of your accounts' proven closing balances (None if no statement has one)."""
    latest = insight.net_worth(conn)["latest"]
    return latest


def list_goals(conn, a=None):
    """Each goal with how far you are, how much a month it needs, and whether your last six months' saving pace gets you there in time."""
    have = _saved_now(conn)
    months = _months(conn)[-6:]
    pace = statistics.mean([m["income"] - m["spent"] for m in months]) if months else None
    today = clock.today()
    out = []
    for g in conn.execute("SELECT id, name, target_minor, by_date FROM goals ORDER BY by_date IS NULL, by_date, id"):
        target = g["target_minor"] / 100
        item = {
            "id": g["id"],
            "name": g["name"],
            "target": target,
            "by": g["by_date"],
            "have": have,
            "percent": round(have / target * 100, 1) if have is not None else None,
        }
        if g["by_date"]:
            left = (date.fromisoformat(g["by_date"]).year - today.year) * 12 + date.fromisoformat(g["by_date"]).month - today.month
            item["months_left"] = max(left, 0)
            if have is not None and left > 0:
                need = max(target - have, 0) / left
                item["needed_per_month"] = round(need, 2)
                item["on_track"] = bool(pace is not None and pace >= need)
        item["pace_per_month"] = round(pace, 2) if pace is not None else None
        out.append(item)
    return {
        "currency": _currency(conn),
        "goals": out,
        "basis": "your total balance now (from proven statements) and your average monthly saving over the last six months",
    }


# ---- forecast ---------------------------------------------------------------------------------------------------------------------
def forecast(conn, a=None):
    """The next months if things carry on as they have: the middle (median) of your last six months' income and spending. An ESTIMATE, labelled as such, never advice."""
    ahead = max(1, min(int((a or {}).get("months", 6)), 24))
    months = _months(conn)[-6:]
    if len(months) < 3:
        return {"currency": _currency(conn), "estimate": True, "months": [], "note": "At least three months of data are needed for an estimate."}
    income = statistics.median(m["income"] for m in months)
    spent = statistics.median(m["spent"] for m in months)
    balance = _saved_now(conn)
    y, m = int(months[-1]["month"][:4]), int(months[-1]["month"][5:])
    series = []
    for _ in range(ahead):
        y, m = y + (m == 12), m % 12 + 1
        balance = None if balance is None else balance + income - spent
        series.append(
            {"month": f"{y}-{m:02d}", "income": round(income, 2), "spent": round(spent, 2), "balance": None if balance is None else round(balance, 2)}
        )
    return {
        "currency": _currency(conn),
        "estimate": True,
        "months": series,
        "basis": f"the median of your last {len(months)} months: money in {income:,.2f}, spent {spent:,.2f}",
        "note": "An estimate from your own recent months. One-off costs and changes to your income are not predicted.",
    }


# ---- timeline ---------------------------------------------------------------------------------------------------------------------
def timeline(conn, a=None):
    """What happened, newest first: salary changes, trips and events, regular payments that started or stopped, and each year's largest payment."""
    items: list[dict] = []
    slips = conn.execute("SELECT period, net_minor FROM payslips WHERE period<>'' ORDER BY period").fetchall()
    for prev, cur in itertools.pairwise(slips):
        if prev["net_minor"] and abs(cur["net_minor"] - prev["net_minor"]) / prev["net_minor"] >= 0.03:
            items.append(
                {
                    "date": cur["period"] + "-01",
                    "what": f"Net salary {'rose' if cur['net_minor'] > prev['net_minor'] else 'fell'} from {prev['net_minor'] / 100:,.2f} to {cur['net_minor'] / 100:,.2f}",
                }
            )
    for e in conn.execute(
        "SELECT e.name, e.main, MIN(t.day) AS first, SUM(CASE WHEN t.kind='expense' THEN t.amount_minor ELSE -t.amount_minor END) AS net FROM events e JOIN transactions t ON t.event_id=e.id GROUP BY e.id"
    ):
        items.append({"date": e["first"], "what": f"{e['name']} ({e['main']}): {e['net'] / 100:,.2f}"})
    oldest, newest = conn.execute("SELECT MIN(day), MAX(day) FROM transactions").fetchone()
    for g in insight._recurring(conn):
        first, last = g["items"][0][0], g["items"][-1][0]
        if (
            oldest and (date.fromisoformat(first) - date.fromisoformat(oldest)).days > 60
        ):  # one that is there from the first month of data began earlier: that date is unknown
            items.append({"date": first, "what": f"{g['merchant'].title()} started ({g['items'][0][1] / 100:,.2f} a month)"})
        if newest and (date.fromisoformat(newest) - date.fromisoformat(last)).days > 75:
            items.append({"date": last, "what": f"{g['merchant'].title()} stopped"})
    for r in conn.execute(
        "SELECT substr(day,1,4) AS y, day, note, MAX(amount_minor) AS amount FROM ledger WHERE kind='expense' AND category<>'transfers' AND event_id IS NULL GROUP BY y"
    ):
        items.append({"date": r["day"], "what": f"Largest payment of {r['y']}: {(r['note'] or '')[:40]}, {r['amount'] / 100:,.2f}"})
    return {"currency": _currency(conn), "items": sorted(items, key=lambda x: x["date"], reverse=True)[:60]}


# ---- things worth a look: suggestions and the detective --------------------------------------------------------------------------------
def suggestions(conn, a=None):
    """Plain rules applied to your own figures. Each says what it saw and the numbers it used; none is financial advice and none comes from a model."""
    out: list[dict] = []
    months = _months(conn)
    last12 = months[-12:]
    if len(last12) >= 6:
        income, spent = sum(m["income"] for m in last12), sum(m["spent"] for m in last12)
        if income > 0:
            rate = (income - spent) / income * 100
            if rate < 0:
                out.append(
                    {
                        "topic": "savings rate",
                        "text": f"In the last {len(last12)} months you spent {spent - income:,.2f} more than came in ({spent:,.2f} spent, {income:,.2f} in).",
                    }
                )
            elif rate < 10:
                out.append(
                    {
                        "topic": "savings rate",
                        "text": f"In the last {len(last12)} months you kept {rate:.0f}% of what came in ({income - spent:,.2f} of {income:,.2f}). Many people aim for 10-20%.",
                    }
                )
        avg = spent / len(last12)
        have = _saved_now(conn)
        if have is not None and avg > 0 and have < 3 * avg:
            out.append(
                {
                    "topic": "buffer",
                    "text": f"Your accounts hold {have:,.2f}, which covers {have / avg:.1f} months of your usual spending of {avg:,.2f}. A common rule of thumb is 3-6 months.",
                }
            )
    rows = conn.execute(
        "SELECT substr(day,1,7) AS m, category, SUM(amount_minor) AS t FROM ledger WHERE kind='expense' AND category<>'transfers' AND event_id IS NULL GROUP BY m, category"
    ).fetchall()
    by: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by[r["category"]][r["m"]] = r["t"] / 100
    latest = months[-1]["month"] if months else ""
    for cat, per in by.items():
        before = [v for k, v in sorted(per.items()) if k < latest][-3:]
        now = per.get(latest, 0)
        if len(before) == 3 and now >= 50 and now > 1.3 * statistics.mean(before):
            out.append(
                {
                    "topic": cat,
                    "text": f"{cat.title()} was {now:,.2f} in {latest}, {now / statistics.mean(before) * 100 - 100:.0f}% above the average of the three months before ({statistics.mean(before):,.2f}).",
                }
            )
    regular = insight._recurring(conn)
    if regular:
        total = sum(statistics.median(x for _, x in g["items"][-3:]) for g in regular) / 100
        income = statistics.median(m["income"] for m in last12) if last12 else 0
        if income and total > 0.5 * income:
            out.append(
                {
                    "topic": "fixed costs",
                    "text": f"Your regular payments come to about {total:,.2f} a month, {total / income * 100:.0f}% of a typical month's income ({income:,.2f}).",
                }
            )
    return {"currency": _currency(conn), "items": out, "note": "Rules applied to your own figures: observations, not advice."}


def money_detective(conn, a=None):
    """Everything odd in one list: payments charged twice, prices that changed, unusually large payments, items that may not be spending, and months that cannot be proven."""
    found = [
        *insight.duplicate_payments(conn),
        *insight.price_changes(conn),
        *insight.unusual_payments(conn),
    ]
    items = [{"kind": f.agent, "text": f.message} for f in found if f.level != "ok"]
    latest = conn.execute("SELECT MAX(substr(day,1,7)) FROM transactions").fetchone()[0]
    if latest:
        for item in insight.month_breakdown(conn, {"month": latest})["look_at"]:
            items.append({"kind": "to check", "text": f"{item['amount']:,.2f} on {item['day']} {item['note']}: {item['why'][0]}"})
        p = proof.month_proof(conn, {"month": latest})
        items += [{"kind": "not proven", "text": r} for r in p["reasons"] if not p["proven"]]
    return {"items": items[:30]}


# ---- budgets, bills, tax, merchants ------------------------------------------------------------------------------------------------
def budget_progress(conn, a=None):
    """Each monthly budget against what was spent in that category in the month (money in a trip or event is not counted: it is one-time)."""
    from . import dates

    month = (a or {}).get("month") or (conn.execute("SELECT MAX(substr(day,1,7)) FROM ledger").fetchone()[0] or clock.today().strftime("%Y-%m"))
    start, end = dates.month_bounds(month)
    spent = {
        r["category"]: r["t"] / 100
        for r in conn.execute(
            "SELECT category, SUM(amount_minor) AS t FROM ledger WHERE kind='expense' AND category<>'transfers' AND event_id IS NULL AND day>=? AND day<? GROUP BY category",
            (start, end),
        )
    }
    out = []
    for b in conn.execute("SELECT category, monthly_minor FROM budgets ORDER BY category"):
        budget, used = b["monthly_minor"] / 100, spent.get(b["category"], 0.0)
        out.append(
            {
                "category": b["category"],
                "budget": budget,
                "spent": round(used, 2),
                "left": round(budget - used, 2),
                "percent": round(used / budget * 100) if budget else None,
                "over": used > budget,
            }
        )
    return {"month": month, "currency": _currency(conn), "budgets": out}


def bills_due(conn, a=None):
    """What is coming: invoices with a due date that no payment of that amount has settled yet, and the regular payments expected soon."""
    days = int((a or {}).get("days", 45))
    today = clock.today()
    bills = []
    for d in conn.execute(
        "SELECT name, party, due_date, doc_date, total_minor FROM finance_docs WHERE kind='invoice' AND due_date IS NOT NULL AND total_minor IS NOT NULL ORDER BY due_date"
    ):
        due = date.fromisoformat(d["due_date"])
        if (due - today).days > days or (today - due).days > 30:
            continue
        paid = conn.execute(
            "SELECT 1 FROM transactions WHERE kind='expense' AND amount_minor=? AND day>=? LIMIT 1",
            (d["total_minor"], (date.fromisoformat(d["doc_date"] or d["due_date"]) - __import__("datetime").timedelta(days=5)).isoformat()),
        ).fetchone()
        if not paid:
            bills.append(
                {"what": d["party"] or d["name"], "amount": d["total_minor"] / 100, "due": d["due_date"], "in_days": (due - today).days, "kind": "invoice"}
            )
    regular = [
        {"what": r["merchant"].title(), "amount": r["amount"], "due": r["due"], "in_days": r["in_days"], "kind": "regular"}
        for r in insight.upcoming_payments(conn, {"days": days})
    ]
    items = sorted([*bills, *regular], key=lambda x: x["due"])
    return {"currency": _currency(conn), "items": items, "total": round(sum(i["amount"] for i in items), 2)}


def tax_summary(conn, a=None):
    """The facts a tax return asks for, for one year, from your documents and statements: income, tax already paid, interest, investments, insurance, assessments
    and the balance of your accounts on 1 January. Facts only: not tax advice, and not a return."""
    year = str((a or {}).get("year") or (conn.execute("SELECT MAX(substr(day,1,4)) FROM transactions").fetchone()[0] or clock.today().year))
    annual = conn.execute(
        "SELECT gross_minor, tax_minor, net_minor FROM finance_docs WHERE kind='annual_statement' AND period LIKE ? ORDER BY doc_date DESC LIMIT 1",
        (year + "%",),
    ).fetchone()
    slips = conn.execute(
        "SELECT COUNT(*) AS n, SUM(gross_minor) AS gross, SUM(tax_minor) AS tax, SUM(net_minor) AS net, SUM(pension_minor) AS pension FROM payslips WHERE period LIKE ?",
        (year + "-%",),
    ).fetchone()
    y = next((r for r in yearly_overview(conn)["years"] if r["year"] == year), None) or {}
    january = [
        {"account": f["account"][-4:], "balance": f["closing_minor"] / 100, "as_of": f["period_end"]}
        for f in conn.execute(
            "SELECT s.account, s.closing_minor, s.period_end FROM statement_files s WHERE s.account<>'' AND s.closing_minor IS NOT NULL AND s.period_end<=? "
            "AND s.period_end=(SELECT MAX(period_end) FROM statement_files WHERE account=s.account AND period_end<=?) AND s.status='verified'",
            (f"{year}-01-01", f"{year}-01-01"),
        )
    ]
    letters = [
        dict(r)
        for r in conn.execute(
            "SELECT name, party, doc_date AS date, total_minor/100.0 AS amount FROM finance_docs WHERE kind='tax' AND doc_date LIKE ? ORDER BY doc_date",
            (year + "%",),
        )
    ]
    return {
        "year": year,
        "currency": _currency(conn),
        "annual_statement": None
        if annual is None
        else {"gross": (annual["gross_minor"] or 0) / 100, "tax_withheld": (annual["tax_minor"] or 0) / 100, "net": (annual["net_minor"] or 0) / 100},
        "payslips": {
            "count": slips["n"],
            "gross": (slips["gross"] or 0) / 100,
            "tax_withheld": (slips["tax"] or 0) / 100,
            "net": (slips["net"] or 0) / 100,
            "pension": (slips["pension"] or 0) / 100,
        },
        "interest_received": y.get("interest", 0),
        "paid_into_investments": y.get("invested", 0),
        "insurance_paid": y.get("insurance", 0),
        "balances_on_1_january": january,
        "tax_letters": letters,
        "note": "Facts from your own documents and statements, as a checklist for a tax return. Not tax advice.",
    }


def merchant_history(conn, a):
    """One shop or payee over time: total, count, per month, and the latest payments."""
    needle = str(a.get("merchant", "")).strip().lower()
    if not needle:
        raise ValueError("which merchant?")
    al = insight._aliases(conn)
    rows = [
        r
        for r in conn.execute("SELECT day, note, amount_minor, category, kind FROM ledger WHERE kind='expense' AND category<>'transfers' ORDER BY day DESC")
        if needle in (insight._name(al, r["note"]) or "") or needle in (r["note"] or "").lower()
    ]
    by_month: dict[str, float] = defaultdict(float)
    for r in rows:
        by_month[r["day"][:7]] += r["amount_minor"] / 100
    return {
        "merchant": needle,
        "currency": _currency(conn),
        "payments": len(rows),
        "total": round(sum(r["amount_minor"] for r in rows) / 100, 2),
        "per_month": [{"month": m, "spent": round(v, 2)} for m, v in sorted(by_month.items())][-24:],
        "latest": [{"day": r["day"], "amount": r["amount_minor"] / 100, "category": r["category"], "note": (r["note"] or "")[:50]} for r in rows[:15]],
    }


# ---- family ------------------------------------------------------------------------------------------------------------------------
def family_money(conn, a=None):
    """Money between you and the people on your People list: payments whose description names them (a whole word, not a part of another word).
    Nothing is guessed from amounts: a payment counts only if the name is printed on it. Totals per person and per year."""
    out = []
    ledger = conn.execute("SELECT day, kind, amount_minor, note FROM ledger WHERE category<>'transfers' AND event_id IS NULL AND source<>'derived'").fetchall()
    for p in conn.execute("SELECT id, name, relation FROM people ORDER BY name"):
        name = p["name"].strip()
        if len(name) < 3:
            continue
        pattern = re.compile(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)")
        mine = [r for r in ledger if pattern.search((r["note"] or "").lower())]
        by_year: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for r in mine:
            by_year[r["day"][:4]][0 if r["kind"] == "expense" else 1] += r["amount_minor"] / 100
        out.append(
            {
                "id": p["id"],
                "name": name,
                "relation": p["relation"],
                "payments": len(mine),
                "sent": round(sum(r["amount_minor"] for r in mine if r["kind"] == "expense") / 100, 2),
                "received": round(sum(r["amount_minor"] for r in mine if r["kind"] == "income") / 100, 2),
                "last": max((r["day"] for r in mine), default=None),
                "by_year": [{"year": y, "sent": round(v[0], 2), "received": round(v[1], 2)} for y, v in sorted(by_year.items())],
            }
        )
    return {"currency": _currency(conn), "people": out, "note": "Counted only where the person's name is printed on the payment."}


# ---- the five sections: income, savings ----------------------------------------------------------------------------------------------
def income_breakdown(conn, a=None):
    """Money in, split into salary, bonus and everything else (interest, refunds, other), by month and by year. Money that belongs to a trip or event is not income."""
    kinds = {"salary": "salary", "bonus": "bonus"}
    months: dict[str, dict[str, float]] = {}
    for r in conn.execute(
        "SELECT substr(day,1,7) AS m, category, SUM(amount_minor) AS t FROM ledger WHERE kind='income' AND category<>'transfers' AND event_id IS NULL GROUP BY m, category"
    ):
        slot = months.setdefault(r["m"], {"salary": 0.0, "bonus": 0.0, "other": 0.0})
        slot[kinds.get(r["category"], "other")] += r["t"] / 100
    rows: list[dict[str, Any]] = [
        {"month": m, **{k: round(v, 2) for k, v in vals.items()}, "total": round(sum(vals.values()), 2)} for m, vals in sorted(months.items())
    ]
    years: dict[str, dict[str, float]] = {}
    for r in rows:
        y = years.setdefault(r["month"][:4], {"salary": 0.0, "bonus": 0.0, "other": 0.0, "total": 0.0})
        for k in ("salary", "bonus", "other", "total"):
            y[k] += r[k]
    year_rows = [{"year": y, **{k: round(v, 2) for k, v in vals.items()}} for y, vals in sorted(years.items())]
    return {"currency": _currency(conn), "months": rows[-24:], "years": year_rows, "latest_year": year_rows[-1] if year_rows else None}


def savings_overview(conn, a=None):
    """What was saved (money in minus spent) and the savings rate (saved / money in), by month and by year. A negative number means more went out than came in."""
    months: list[dict[str, Any]] = []
    for m in _months(conn):
        saved = m["income"] - m["spent"]
        months.append(
            {
                "month": m["month"],
                "income": round(m["income"], 2),
                "spent": round(m["spent"], 2),
                "saved": round(saved, 2),
                "rate": round(saved / m["income"] * 100, 1) if m["income"] > 0 else None,
            }
        )
    years = [{k: y[k] for k in ("year", "income", "spent", "saved", "savings_rate", "months")} for y in yearly_overview(conn)["years"]]
    last12 = months[-12:]
    income, spent = sum(m["income"] for m in last12), sum(m["spent"] for m in last12)
    rated = [m for m in last12 if m["rate"] is not None]
    return {
        "currency": _currency(conn),
        "months": months[-24:],
        "years": years,
        "latest_year": years[-1] if years else None,
        "last12": {
            "months": len(last12),
            "income": round(income, 2),
            "spent": round(spent, 2),
            "saved": round(income - spent, 2),
            "rate": round((income - spent) / income * 100, 1) if income > 0 else None,
        },
        "best": max(rated, key=lambda m: m["rate"], default=None),
        "worst": min(rated, key=lambda m: m["rate"], default=None),
    }
