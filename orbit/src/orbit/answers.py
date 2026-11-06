"""The check on every answer: a figure in a reply must come from a tool that ran (and match the ledger), and the data-health note is added.

The model writes the answer; this decides whether it can be shown. It never writes an answer itself."""

from __future__ import annotations

from kit.audit import unproven_figures

from .modules import ALL, tools

MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def _label(month: str) -> str:
    year, number = month.split("-")
    return f"{MONTH_NAMES[int(number) - 1]} {year}"


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
    from . import toolrun

    out = []
    for name, args, seen in calls:
        if name in REPORTS:
            again, error = toolrun.run_tool(conn, name, args)
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


def check_tool(conn, name: str, args: dict, output: str) -> tuple[list[str], list[str]]:
    """The check on one report a tool just produced: its months must tie to the raw ledger (else it is not shown at all), and a month that is not
    proven or files waiting for a check are said next to it. Other tools need no check."""
    if name not in REPORTS:
        return [], []
    calls = [(name, args, output)]
    return _untied(conn, calls, None), [*_proof_notes(conn, calls, None), *_health_note(conn)]
