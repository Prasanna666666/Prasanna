"""Instant, exact answers to the money questions people ask most. Code runs the tools and writes the sentence: no model is involved, so the answer is
always complete, always right to the cent, and takes milliseconds. Anything this does not recognise goes to the assistant (which has a time limit)."""

from __future__ import annotations

import re
from datetime import date

from .modules import ALL, tools

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£", "INR": "₹"}
ADVICE = re.compile(r"\b(why|should|advice|advise|recommend|suggest|how can i|how do i|what if|plan|budget|save more|explain)\b")


def _m(x: float, cur: str) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}{SYMBOL.get(cur, cur + ' ')}{abs(x):,.2f}"


def _month(text: str, months: list[str]) -> str | None:
    """The month asked about: 'last month' is the one before the newest with data; a month name picks that month (newest year that has it)."""
    if not months:
        return None
    t = text.lower()
    if "last month" in t or "previous month" in t:
        return months[-2] if len(months) > 1 else months[-1]
    for name, n in MONTHS.items():
        if re.search(rf"\b{name}\b|\b{name[:3]}\b(?!\w)", t) and (name != "may" or re.search(r"\bmay\b", t)):
            year = re.search(r"\b(20\d{2})\b", t)
            hits = [m for m in months if int(m[5:]) == n and (not year or m[:4] == year.group(1))]
            return hits[-1] if hits else f"none:{name}"
    return months[-1]  # statements arrive after the month ends: the newest month with data is "now"


def _label(month: str) -> str:
    y, m = month.split("-")
    return f"{list(MONTHS)[int(m) - 1].title()} {y}"


def answer(conn, text: str) -> str | None:
    """A complete answer, or None if this question needs the assistant."""
    t = " ".join(text.lower().split())
    asking = "?" in t or re.match(r"(how|what|which|where|when|who|show|list|tell|give|any|is|are|do|did|can)\b", t)
    if not t or not asking or ADVICE.search(t) or len(t) > 160:
        return None  # not a question (for example "I spent 100 on food" is a note to record), or one that needs thinking
    T = tools(ALL)
    run = lambda name, a=None: T[name].fn(conn, a or {})  # noqa: E731
    trend = run("monthly_trend", {"months": 120})
    months = [r["month"] for r in trend]
    cur = run("currencies") if False else None  # noqa: F841
    has = lambda *words: any(re.search(rf"\b{w}", t) for w in words)  # noqa: E731

    if has("coming up", "upcoming", "next bill", "due soon", "bills due", "what.?s due", "payments due"):
        rows = run("upcoming_payments", {"days": 45})
        if not rows:
            return "No regular payments are due in the next 45 days."
        return "Coming up:\n" + "\n".join(f"- {r['merchant'].title()}: {_m(r['amount'], r['currency'])} on {r['due']}" for r in rows)
    if has("regular", "recurring", "subscription", "every month", "monthly payment", "fixed cost"):
        rows = run("recurring_payments")
        if not rows:
            return "I don't see any payments that repeat every month yet."
        total = sum(r["per_month"] for r in rows)
        return f"Your regular payments come to about {_m(total, 'EUR')} a month:\n" + "\n".join(f"- {r['merchant'].title()}: {_m(r['typical_amount'], 'EUR')}" for r in rows[:10])
    if has("top merchant", "biggest", "most money", "where does my money", "where did my money", "spend the most", "spent the most", "top spend"):
        rows = run("top_merchants")[:8]
        return "Where most of your money went:\n" + "\n".join(f"- {r['merchant'].title()}: {_m(r['spent'], 'EUR')} ({r['times']}x)" for r in rows) if rows else "No payments yet."
    if has("net worth", "balance", "how much do i have", "how much money do i have", "my accounts"):
        nw = run("net_worth")
        if nw["latest"] is None:
            return "I can't show balances yet: no statement has been proven with a closing balance."
        lines = [f"- {a['account']}: {_m(a['balance'], a['currency'])}" + (f" (about {_m(a['eur'], 'EUR')})" if a["currency"] != "EUR" and a["eur"] is not None else "") + f", as of {a['as_of']}" for a in nw["accounts"]]
        return f"All your accounts together: {_m(nw['latest'], 'EUR')}.\n" + "\n".join(lines)
    if has("problem", "wrong", "verified", "verify", "tally", "tallies", "check", "mistake", "reliable", "trust"):
        bad = run("files_to_check")
        rep = run("verification_report")
        fails = [f for f in rep.get("findings", []) if f.get("level") == "fail"] if isinstance(rep, dict) else []
        if not bad and not fails:
            return "Everything I read adds up: no file needs a check and no cross-check failed."
        return f"{len(bad)} file(s) need a check and {len(fails)} cross-check(s) failed. Open Money > Files to see which."
    if has("income", "earn", "salary", "paid me", "money in", "received", "payslip"):
        month = _month(t, months)
        if month is None or month.startswith("none:"):
            return "I don't have that month yet."
        r = run("income_summary", {"month": month})
        if not r["sources"] and not r["payslip"]:
            return f"No money in for {_label(month)}."
        parts = [f"Money in for {_label(month)}: {_m(r['total'], 'EUR')}."] + [f"- {s['source'].title()}: {_m(s['amount'], 'EUR')}" for s in r["sources"]]
        if r["payslip"]:
            p = r["payslip"]
            parts.append(f"Payslip: gross {_m(p['gross'], 'EUR')}, tax {_m(p['tax'] or 0, 'EUR')}, net {_m(p['net'], 'EUR')}.")
        return "\n".join(parts)
    if has("month by month", "trend", "compare", "history", "each month", "per month"):
        rows = trend[-6:]
        return "Last months (spent / money in):\n" + "\n".join(f"- {_label(r['month'])}: {_m(r['spent'], 'EUR')} / {_m(r['income'], 'EUR')}" for r in rows) if rows else "No data yet."
    if has("spend", "spent", "spending", "cost", "expense", "paid for", "how much"):
        month = _month(t, months)
        if month is None:
            return "No payments yet. Add your statements and tap Read my files."
        if month.startswith("none:"):
            return f"I don't have {month[5:].title()} yet."
        s = run("spending_summary", {"month": month})
        cats = {c["category"]: c["spent"] for c in s["by_category"]}
        asked = [c for c in cats if re.search(rf"\b{re.escape(c)}", t)]
        cur = s.get("currency", "EUR")
        if asked:
            return "\n".join(f"{_label(month)}: {c} {_m(cats[c], cur)}." for c in asked)
        top = "\n".join(f"- {c['category'].title()}: {_m(c['spent'], cur)}" for c in s["by_category"][:6])
        return f"You spent {_m(s['spent'], cur)} in {_label(month)} (money in {_m(s['income'], cur)}).\n{top}"
    return None


def render_any(data) -> str:
    """A readable text for any tool result, used when the assistant ran out of time after a tool had already answered."""
    if isinstance(data, list):
        return "\n".join("- " + ", ".join(f"{k}: {v}" for k, v in row.items() if v not in (None, "")) if isinstance(row, dict) else f"- {row}" for row in data[:10]) or "Nothing found."
    if isinstance(data, dict):
        return "\n".join(f"{k}: {v}" for k, v in data.items() if not isinstance(v, (list, dict)) and v not in (None, ""))
    return str(data)


_ = date
