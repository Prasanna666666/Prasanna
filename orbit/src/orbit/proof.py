"""Is this month PROVEN? Every number Orbit shows is only as good as the statements behind it, so for each month it says plainly either
"proven" or "not proven, and here is why". Proven means ALL of the following hold, for every account that has payments in the month:

  1. a statement covers the whole month (no gap between statements longer than five days);
  2. every one of those statements passed its own proofs (balances add up, three PDF engines agree, a second reading agrees);
  3. each statement's closing balance equals the next one's opening balance;
  4. every payment belongs to a known account;
  5. the month's reports equal the raw ledger to the cent;
  6. no cross-check has failed.

Anything less is "not proven", with each reason listed. Nothing here guesses: it only reads what the other checks already established."""

from __future__ import annotations

import itertools
from datetime import date, timedelta

from . import dates, verify

GAP_DAYS = 5


def _covered(files: list, start: date, end: date) -> bool:
    """Do these statements, taken together, cover [start, end) with no gap longer than GAP_DAYS?"""
    spans = sorted((date.fromisoformat(f["period_start"]), date.fromisoformat(f["period_end"])) for f in files)
    if not spans or spans[0][0] > start + timedelta(days=GAP_DAYS) or max(e for _, e in spans) < end - timedelta(days=1 + GAP_DAYS):
        return False
    return all((b[0] - a[1]).days <= GAP_DAYS or b[0] <= a[1] for a, b in itertools.pairwise(spans))


def month_proof(conn, a=None):
    a = a or {}
    month = a.get("month") or (conn.execute("SELECT MAX(substr(day,1,7)) FROM transactions").fetchone()[0] or "")
    if not month:
        return {"month": "", "proven": False, "reasons": ["there are no payments yet"], "accounts": 0}
    start_s, end_s = dates.month_bounds(month)
    start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
    reasons: list[str] = []
    in_month = "day>=? AND day<?"
    unknown = conn.execute(f"SELECT COUNT(*) FROM transactions WHERE account='' AND {in_month}", (start_s, end_s)).fetchone()[0]
    if unknown:
        reasons.append(f"{unknown} payment(s) belong to no known account (entered by hand, or the account was not printed on the statement)")
    accounts = [r[0] for r in conn.execute(f"SELECT DISTINCT account FROM transactions WHERE account<>'' AND {in_month}", (start_s, end_s))]
    for acc in sorted(accounts):
        files = list(
            conn.execute(
                "SELECT name, status, period_start, period_end, opening_minor, closing_minor FROM statement_files "
                "WHERE account=? AND period_start IS NOT NULL AND period_end>=? AND period_start<? ORDER BY period_start",
                (acc, start_s, end_s),
            )
        )
        if not files or not _covered(files, start, end):
            reasons.append(f"account {acc[-4:]}: no statement covers all of {month}")
            continue
        reasons += [
            f"{f['name']}: {'its balances could not be proven' if f['status'] == 'unverified' else 'it needs a check'}"
            for f in files
            if f["status"] != "verified"
        ]
        every = list(
            conn.execute(
                "SELECT name, period_start, closing_minor, opening_minor FROM statement_files WHERE account=? AND period_start IS NOT NULL ORDER BY period_start",
                (acc,),
            )
        )
        names = {f["name"] for f in files}
        for x, y in itertools.pairwise(every):  # the join with the statement before and the one after counts too
            if (
                (x["name"] in names or y["name"] in names)
                and x["closing_minor"] is not None
                and y["opening_minor"] is not None
                and x["closing_minor"] != y["opening_minor"]
            ):
                reasons.append(f"account {acc[-4:]}: {x['name']} ends at a different balance than {y['name']} starts with")
    why = verify.tally_month(conn, month)
    if why:
        reasons.append(f"the reports do not match the ledger: {why}")
    fails = conn.execute("SELECT agent, message FROM findings WHERE level='fail' AND cross=1").fetchall()
    reasons += [f"{f['agent']}: {f['message']}" for f in fails[:5]]
    return {"month": month, "proven": not reasons, "accounts": len(accounts), "reasons": list(dict.fromkeys(reasons))[:12]}
