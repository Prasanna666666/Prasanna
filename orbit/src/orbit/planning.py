"""The planning side of Orbit: years, savings, goals, forecast, timeline, interest, investments, insurance and things worth a look.

Every number here is computed from the same proven ledger as the rest of the app, by exact arithmetic. Nothing is invented: a forecast is a labelled estimate
from your own recent months, a suggestion is a rule applied to your figures (and says which), and anything that needs data Orbit does not have (the value of an
investment portfolio, for example) says so instead of guessing."""

from __future__ import annotations

import itertools
import statistics
from collections import defaultdict
from datetime import date

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
    """Interest received per year, and an estimated yearly rate for each account that earns it: interest / the average of its closing balances."""
    rows = conn.execute(
        "SELECT substr(day,1,4) AS y, account, SUM(amount_minor) AS t FROM ledger WHERE kind='income' AND category='interest' GROUP BY y, account"
    ).fetchall()
    out = []
    for r in rows:
        balances = [
            x["closing_minor"]
            for x in conn.execute(
                "SELECT closing_minor FROM statement_files WHERE account=? AND substr(period_end,1,4)=? AND closing_minor IS NOT NULL", (r["account"], r["y"])
            )
        ]
        average = statistics.mean(balances) if balances else None
        out.append(
            {
                "year": r["y"],
                "account": (r["account"] or "")[-4:],
                "interest": r["t"] / 100,
                "average_balance": round(average / 100, 2) if average else None,
                "rate_percent": round(r["t"] / average * 100, 2) if average and average > 0 else None,
                "note": "estimate: interest divided by the average of the statements' closing balances" if average else "no balances to compare with",
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
