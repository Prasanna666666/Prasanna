"""The safety net behind the assistant. The agents answer first; this takes over when an agent is too slow, the model is off, or its reply contains a
figure that no tool returned. Code runs the same tools and writes the sentence, so the answer is complete and right to the cent."""

from __future__ import annotations

import re

from .modules import ALL, tools

MONTHS = {
    m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)
}
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


class _Ask:
    """One question being answered: the tools it may run, its words, and the months its answer is about."""

    def __init__(self, conn, text: str, used: list) -> None:
        self.text, self.used, self._tools, self.conn = text, used, tools(ALL), conn
        self.months = [r["month"] for r in self.run("monthly_trend", {"months": 120})]
        self.used_month = False  # did the answer apply the month named in the question?
        self.used_words: set[str] = set()  # category names the answer applied

    def run(self, name: str, args: dict | None = None):
        return self._tools[name].fn(self.conn, args or {})

    def has(self, *words: str) -> bool:
        return any(re.search(rf"\b{w}", self.text) for w in words)

    def month(self) -> str | None:
        self.used_month = True
        return _month(self.text, self.months)


def _upcoming(q: _Ask) -> str:
    rows = q.run("upcoming_payments", {"days": 45})
    if not rows:
        return "No regular payments are due in the next 45 days."
    return "Coming up:\n" + "\n".join(f"- {r['merchant'].title()}: {_m(r['amount'], r['currency'])} on {r['due']}" for r in rows)


def _regular(q: _Ask) -> str:
    rows = q.run("recurring_payments")
    if not rows:
        return "I don't see any payments that repeat every month yet."
    total = sum(r["per_month"] for r in rows)
    return f"Your regular payments come to about {_m(total, 'EUR')} a month:\n" + "\n".join(
        f"- {r['merchant'].title()}: {_m(r['typical_amount'], 'EUR')}" for r in rows[:10]
    )


def _top_merchants(q: _Ask) -> str:
    rows = q.run("top_merchants")[:8]
    if not rows:
        return "No payments yet."
    return "Where most of your money went:\n" + "\n".join(f"- {r['merchant'].title()}: {_m(r['spent'], 'EUR')} ({r['times']}x)" for r in rows)


def _net_worth(q: _Ask) -> str:
    nw = q.run("net_worth")
    if nw["latest"] is None:
        return "I can't show balances yet: no statement has been proven with a closing balance."
    lines = [
        f"- {a['account']}: {_m(a['balance'], a['currency'])}"
        + (f" (about {_m(a['eur'], 'EUR')})" if a["currency"] != "EUR" and a["eur"] is not None else "")
        + f", as of {a['as_of']}"
        for a in nw["accounts"]
    ]
    return f"All your accounts together: {_m(nw['latest'], 'EUR')}.\n" + "\n".join(lines)


def _problems(q: _Ask) -> str:
    bad = q.run("files_to_check")
    rep = q.run("verification_report")
    fails = [f for f in rep.get("findings", []) if f.get("level") == "fail"] if isinstance(rep, dict) else []
    if not bad and not fails:
        return "Everything I read adds up: no file needs a check and no cross-check failed."
    return f"{len(bad)} file(s) need a check and {len(fails)} cross-check(s) failed. Open Money > Files to see which."


def _income(q: _Ask) -> str:
    month = q.month()
    if month is None or month.startswith("none:"):
        return "I don't have that month yet."
    q.used.append(month)
    r = q.run("income_summary", {"month": month})
    if not r["sources"] and not r["payslip"]:
        return f"No money in for {_label(month)}."
    parts = [f"Money in for {_label(month)}: {_m(r['total'], 'EUR')}."] + [f"- {s['source'].title()}: {_m(s['amount'], 'EUR')}" for s in r["sources"]]
    if r["payslip"]:
        p = r["payslip"]
        parts.append(f"Payslip: gross {_m(p['gross'], 'EUR')}, tax {_m(p['tax'] or 0, 'EUR')}, net {_m(p['net'], 'EUR')}.")
    return "\n".join(parts)


def _trend(q: _Ask) -> str:
    rows = q.run("monthly_trend", {"months": 6})
    if not rows:
        return "No data yet."
    return "Last months (spent / money in):\n" + "\n".join(f"- {_label(r['month'])}: {_m(r['spent'], 'EUR')} / {_m(r['income'], 'EUR')}" for r in rows)


def _spending(q: _Ask) -> str:
    month = q.month()
    if month is None:
        return "No payments yet. Add your statements and tap Read my files."
    if month.startswith("none:"):
        return f"I don't have {month[5:].title()} yet."
    q.used.append(month)
    s = q.run("spending_summary", {"month": month})
    cats = {c["category"]: c["spent"] for c in s["by_category"]}
    asked = [c for c in cats if re.search(rf"\b{re.escape(c)}", q.text)]
    q.used_words.update(asked)
    cur = s.get("currency", "EUR")
    if asked:
        return "\n".join(f"{_label(month)}: {c} {_m(cats[c], cur)}." for c in asked)
    top = "\n".join(f"- {c['category'].title()}: {_m(c['spent'], cur)}" for c in s["by_category"][:6])
    split = q.run("month_breakdown", {"month": month})
    parts = f" (monthly {_m(split['monthly'], cur)}, one-time {_m(split['one_time'], cur)})" if split["one_time"] else ""
    return f"You spent {_m(s['spent'], cur)} in {_label(month)}{parts}; money in {_m(s['income'], cur)}.\n{top}"


# the first group of words that matches picks the answer, so the more specific questions come first
INTENTS = (
    (("coming up", "upcoming", "next bill", "due soon", "bills due", "what.?s due", "payments due"), _upcoming),
    (("regular", "recurring", "subscription", "every month", "monthly payment", "fixed cost"), _regular),
    (("top merchant", "biggest", "most money", "where does my money", "where did my money", "spend the most", "spent the most", "top spend"), _top_merchants),
    (("net worth", "balance", "how much do i have", "how much money do i have", "my accounts"), _net_worth),
    (("problem", "wrong", "verified", "verify", "tally", "tallies", "check", "mistake", "reliable", "trust"), _problems),
    (("income", "earn", "salary", "paid me", "money in", "received", "payslip"), _income),
    (("month by month", "trend", "compare", "history", "each month", "per month"), _trend),
    (("spend", "spent", "spending", "cost", "expense", "paid for", "how much"), _spending),
)


# words that only frame a question and add no condition to it
FRAME = frozenset(
    [
        "a",
        "an",
        "the",
        "i",
        "me",
        "my",
        "mine",
        "we",
        "our",
        "you",
        "your",
        "is",
        "are",
        "was",
        "were",
        "be",
        "am",
        "do",
        "does",
        "did",
        "how",
        "what",
        "which",
        "when",
        "where",
        "who",
        "much",
        "many",
        "in",
        "of",
        "for",
        "on",
        "at",
        "to",
        "from",
        "by",
        "please",
        "can",
        "could",
        "tell",
        "show",
        "give",
        "list",
        "any",
        "all",
        "there",
        "it",
        "its",
        "that",
        "this",
        "last",
        "previous",
        "month",
        "money",
        "total",
        "now",
        "with",
        "payments",
        "payment",
        "bills",
        "bill",
        "files",
        "file",
        "accounts",
        "account",
    ]
)
MONTH_WORDS = frozenset([*MONTHS, *(m[:3] for m in MONTHS)])


def _fully_understood(q: _Ask, intent_words: tuple[str, ...]) -> bool:
    """Code may answer only when every word of the question is accounted for: the intent's own words, plain framing, and the month and categories the
    answer actually applied. Anything left over (a merchant, "more than", "and", "together", a year or a week) is a condition the answer would
    silently ignore, so the question goes to the assistant instead."""
    rest = q.text
    for w in intent_words:
        rest = re.sub(rf"\b{w}\w*", " ", rest)
    tokens = re.findall(r"[^\W\d_]+|\d+", rest)
    named = {t for t in tokens if t in MONTH_WORDS}
    if len(named) > 1 or (named and not q.used_month):
        return False
    left = [
        t
        for t in tokens
        if t not in FRAME and t not in named and t not in q.used_words and not (t.isdigit() and len(t) == 4 and q.used_month and t.startswith("20"))
    ]
    return not left


def answer(conn, text: str, used: list | None = None) -> str | None:
    """A complete answer, or None if this question needs the assistant. The months it is about are appended to `used` so they can be checked."""
    t = " ".join(text.lower().split())
    asking = "?" in t or re.match(r"(how|what|which|where|when|who|show|list|tell|give|any|is|are|do|did|can)\b", t)
    if not t or not asking or ADVICE.search(t) or len(t) > 160:
        return None  # not a question (for example "I spent 100 on food" is a note to record), or one that needs thinking
    q = _Ask(conn, t, used if used is not None else [])
    for words, handler in INTENTS:
        if q.has(*words):
            reply = handler(q)
            return reply if _fully_understood(q, words) else None
    return None


def render_any(data) -> str:
    """A readable text for any tool result, used when the assistant ran out of time after a tool had already answered."""
    if isinstance(data, list):
        return (
            "\n".join(
                "- " + ", ".join(f"{k}: {v}" for k, v in row.items() if v not in (None, "")) if isinstance(row, dict) else f"- {row}" for row in data[:10]
            )
            or "Nothing found."
        )
    if isinstance(data, dict):
        return "\n".join(f"{k}: {v}" for k, v in data.items() if not isinstance(v, (list, dict)) and v not in (None, ""))
    return str(data)


_NUM = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+\.\d+|(?<![\w.])\d{3,}")


def _numbers(text: str) -> set[float]:
    return {float(m.replace(",", "")) for m in _NUM.findall(text)}


def unproven_figures(reply: str, tool_outputs: list[str]) -> list[float]:
    """Figures in the agent's reply (amounts with decimals or thousands, and any number of 3+ digits) that no tool returned. Dates and years are ignored.
    A figure counts as proven if a tool returned it, or its rounded or whole-number form. Empty if the agent used no tool: it then states no data of yours."""
    if not tool_outputs:
        return []
    seen: set[float] = set()
    for out in tool_outputs:
        for v in re.findall(r"-?\d+(?:\.\d+)?", out):
            x = abs(float(v))
            seen |= {x, round(x), round(x, 1), round(x, 2)}
    text = re.sub(r"\b(?:19|20)\d{2}(?:-\d{2}){0,2}\b", " ", reply)
    return sorted(n for n in _numbers(text) if n not in seen and round(n) not in seen)


# ---- the answer checker: runs on every answer, whoever wrote it ----------------------------------------------------------------
REPORTS = frozenset(
    {
        "spending_summary",
        "income_summary",
        "daily_spending",
        "spending_by_main",
        "monthly_trend",
        "top_merchants",
        "recurring_payments",
        "upcoming_payments",
        "net_worth",
        "list_transactions",
        "list_events",
        "list_payslips",
        "uncategorised_spending",
    }
)


def _calls(turns: list[dict]) -> list[tuple[str, dict, str]]:
    """(tool, arguments, what it returned) for every tool the agent used in this answer."""
    out, pending = [], []
    for m in turns:
        for c in m.get("tool_calls") or []:
            pending.append((c["function"]["name"], c["function"].get("arguments") or {}))
        if m.get("role") == "tool" and pending:
            name, args = pending.pop(0)
            out.append((name, args if isinstance(args, dict) else {}, m.get("content") or ""))
    return out


_MONTHLY = ("spending_summary", "income_summary", "daily_spending", "spending_by_main")


def _stale(conn, calls) -> list[str]:
    """Each report the agent used must give exactly the same result when run again now: if not, the data changed under the answer."""
    from . import agent

    out = []
    for name, args, seen in calls:
        if name in REPORTS:
            again, error = agent.run_tool(conn, name, args)
            if error or again != seen:
                out.append(f"{name} gives a different result now than when it was read")
    return out


def _untied(conn, calls, months: list[str] | None) -> list[str]:
    """Every month the answer is about must tie, to the cent, to the raw ledger."""
    from . import verify

    named = sorted({str(a["month"])[:7] for _, a, _ in calls if a.get("month")} | set(months or []))
    if not named and any(n in _MONTHLY for n, _, _ in calls):  # a report with no month named: its default month is the newest with data
        named = [r["month"] for r in tools(ALL)["monthly_trend"].fn(conn, {"months": 1})]
    return [f"{m}: {why}" for m in named if (why := verify.tally_month(conn, m))]


def _health_note(conn) -> list[str]:
    waiting = conn.execute("SELECT COUNT(*) FROM statement_files WHERE status IN ('needs_check','unverified')").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM findings WHERE level='fail'").fetchone()[0]
    if waiting or failed:
        return [f"{waiting} file(s) are waiting for a check and {failed} check(s) have failed, so these figures may be incomplete (see Money > Files)."]
    return []


def _proof_notes(conn, calls, months: list[str] | None) -> list[str]:
    """A month that is not proven is said to be so, with the first reason, next to any figure from it."""
    from . import proof

    named = sorted({str(a["month"])[:7] for _, a, _ in calls if a.get("month")} | set(months or []))
    notes = []
    for m in named:
        p = proof.month_proof(conn, {"month": m})
        if not p["proven"]:
            notes.append(f"{_label(m)} is NOT PROVEN: {p['reasons'][0]}.")
    return notes


def audit(conn, reply: str, turns: list[dict], months: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Check an answer against your data at this moment. Returns (problems, notes).
    A problem means the answer must not be shown. A note is something you must be told alongside it.
      1. every figure in the reply was returned by a tool;
      2. each report the agent used still gives the same result when run again now;
      3. every month the answer is about still ties, to the cent, to the raw ledger;
      4. no file is waiting for a check and no cross-check has failed (else you are told the figures may be incomplete)."""
    calls = _calls(turns)
    problems = []
    bad = unproven_figures(reply, [c[2] for c in calls])
    if bad:
        problems.append("figures not returned by any tool: " + ", ".join(f"{n:,.2f}" for n in bad[:4]))
    problems += _stale(conn, calls) + _untied(conn, calls, months)
    return problems, [*_proof_notes(conn, calls, months), *_health_note(conn)]
