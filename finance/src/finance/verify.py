"""Verifier agents: independent checkers that look at the same facts in different ways. Any one of them can fail a file.

File level (run when a statement is read):   layout reader · balance prover · totals prover · second reader · standard reader
Across documents (run after every import):    payslip <-> bank · invoice/receipt <-> bank · statement continuity per account · plausibility

Each agent returns Findings: ok (it checked and it holds), warn (it could not check, or something deserves a look), fail (a contradiction).
A statement with a fail is NOT counted in your totals. Everything is arithmetic or an exact comparison; the model is only used to describe layouts.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from datetime import date, timedelta

from kit.amounts import money_from_printed

from . import clock, tables
from . import currency as currencies
from .findings import Finding, Read
from .statements import Txn


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def signature(txns: list[Txn]) -> list[tuple]:
    return sorted((t.day, t.amount_minor, t.kind) for t in txns)


# ---- file-level agents -----------------------------------------------------------------------------------------------------
def totals_prover(layout: tables.Layout, text: str, txns: list[Txn], subject: str) -> tuple[Finding | None, bool]:
    """Previous/opening balance + the transactions must equal the new/closing balance, both quoted as printed. Works without a running balance (credit cards)."""
    if not layout.opening_text or not layout.closing_text:
        return None, False
    haystack = _squash(text)
    values = []
    for printed in (layout.opening_text, layout.closing_text):
        minor = money_from_printed(printed) if _squash(printed) in haystack else None
        if minor is None:
            return Finding("totals prover", "warn", subject, "the printed opening/closing balance could not be found in the document"), False
        values.append(minor)
    opening, closing = values
    spent = sum(t.amount_minor for t in txns if t.kind == "expense")
    received = sum(t.amount_minor for t in txns if t.kind == "income")
    expected = opening + spent - received if layout.owed else opening + received - spent  # a card balance is what you owe: purchases raise it
    if expected == closing:
        return Finding("totals prover", "ok", subject, "opening balance + the transactions = the printed closing balance"), True
    return Finding("totals prover", "fail", subject, f"opening + transactions gives {expected / 100:.2f} but the statement prints {closing / 100:.2f}"), False


def second_reader(client, model: str, table: list[list[tables.Cell]], first_layout: tables.Layout, first: tables.Parsed, subject: str) -> Finding:
    """Read the file again from a different part of it. The layout is worked out afresh and both readings must give exactly the same transactions."""
    start = first_layout.header_line
    middle = max(start + 1, len(table) // 2)
    sample = ([table[start]] if start >= 0 else []) + table[middle : middle + 35]
    if len(sample) < 3:
        return Finding("second reader", "warn", subject, "the file is too short for a second, independent reading")
    again = tables.infer_layout(client, model, sample)
    if again is None:
        return Finding("second reader", "warn", subject, "a second reading of the layout was not possible")
    again.header_line = start  # the sample's own header index is relative to the sample
    try:
        other = tables.parse_table(table, again)
    except (ValueError, IndexError):
        return Finding("second reader", "fail", subject, "the second reading could not read the file at all")
    if signature(other.txns) == signature(first.txns):
        return Finding("second reader", "ok", subject, f"a second, independent reading of the layout gives the same {len(first.txns)} transactions")
    return Finding("second reader", "fail", subject, f"two independent readings of the layout disagree ({len(first.txns)} vs {len(other.txns)} transactions)")


_FIGURE = re.compile(r"\d[\d.,' ]*\d|\d")


def _figures(table: list[list[tables.Cell]]) -> Counter:
    """Every printed figure (amounts, dates, balances) with how many times it appears: the fingerprint of what an engine saw."""
    return Counter(re.sub(r"[ ']", "", m) for line in table for c in line for m in _FIGURE.findall(c.text))


def engine_agreement(name: str, data: dict, layout: tables.Layout, first: tables.Parsed) -> list[Finding]:
    """The same PDF read by independent engines (PyMuPDF, pdfminer, poppler). Every printed figure must appear the same number of times in each reading,
    and the same column layout must give exactly the same transactions from each. One engine misreading a digit or dropping a line shows up here."""
    if not isinstance(data.get("table"), list):
        return []  # not a PDF text layer (a spreadsheet, CSV or scan has no second engine)
    alts = {k[6:]: v for k, v in data.items() if k.startswith("table_") and isinstance(v, list)}
    if not alts:
        return [Finding("engine agreement", "warn", name, "only one PDF engine could read this file, so the reading was not compared with another")]
    base_table = tables.table_from_data(data)
    base = _figures(base_table)
    out = []
    for engine, raw in alts.items():
        table = tables.table_from_data({"table": raw})
        theirs = _figures(table)
        if theirs != base:
            lost, extra = base - theirs, theirs - base
            out.append(
                Finding(
                    "engine agreement",
                    "fail",
                    name,
                    f"{engine} sees different figures than the main reader ({sum(lost.values())} missing, {sum(extra.values())} extra): check this file",
                )
            )
            continue
        try:
            other = tables.parse_table(table, layout)
        except (ValueError, IndexError):
            out.append(Finding("engine agreement", "fail", name, f"{engine} could not be read with the same layout"))
            continue
        if signature(other.txns) != signature(first.txns):
            out.append(
                Finding("engine agreement", "fail", name, f"{engine} gives different transactions ({len(other.txns)} vs {len(first.txns)}): check this file")
            )
        else:
            out.append(Finding("engine agreement", "ok", name, f"{engine} reads the same {len(first.txns)} transactions and the same figures"))
    return out


def read_table_statement(client, model: str, name: str, data: dict, text: str) -> Read:
    """A PDF or CSV statement: layout by the model, figures by code, then every agent has its say."""
    r = Read()
    table = tables.table_from_data(data)
    layout, why = tables.infer_layout_why(client, model, table)
    if layout is None:
        r.issues = [f"the layout of this file could not be understood: {why}"]
        r.findings.append(Finding("layout reader", "fail", name, r.issues[0]))
        return r
    parsed = tables.parse_table(table, layout)
    r.txns, r.issues = parsed.txns, list(parsed.issues)
    r.opening, r.closing, r.proofs = parsed.opening, parsed.closing, list(parsed.proofs)
    r.account = layout.account if layout.account and _squash(layout.account) in _squash(text) else ""  # an account number counts only if it is really printed
    r.currency = currencies.detect(text + " " + " ".join(c.text for line in table for c in line))
    r.findings.append(
        Finding("currency", "ok", name, f"the statement is in {r.currency}")
        if r.currency
        else Finding("currency", "warn", name, "the statement does not clearly say which currency it is in; the main currency was assumed")
    )
    if r.txns:
        days = sorted(t.day for t in r.txns)
        r.first, r.last = days[0], days[-1]
    r.findings.append(
        Finding("layout reader", "ok" if not r.issues else "fail", name, f"{len(parsed.txns)} transactions read" if not r.issues else "; ".join(r.issues[:3]))
    )
    if parsed.checked:
        r.findings.append(Finding("balance prover", "ok", name, f"{parsed.checked} running-balance checks all add up"))
    elif not r.issues:
        r.findings.append(Finding("balance prover", "warn", name, "this statement shows no balances to check the lines against"))
    finding, proven = totals_prover(layout, text, r.txns, name)
    if finding:
        r.findings.append(finding)
        if finding.level == "fail":
            r.issues.append(finding.message)
        elif proven:
            r.proofs.append("opening + transactions = closing")
    for finding in engine_agreement(name, data, layout, parsed):
        r.findings.append(finding)
        if finding.level == "fail":
            r.issues.append(finding.message)
    if not r.issues and r.txns:
        second = second_reader(client, model, table, layout, parsed, name)
        r.findings.append(second)
        if second.level == "fail":
            r.issues.append(second.message)
    r.proofs = list(dict.fromkeys(r.proofs))
    r.status = "needs_check" if r.issues else ("verified" if r.proofs else "unverified")
    return r


# ---- across documents ------------------------------------------------------------------------------------------------------
def _months_with_transactions(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT substr(day,1,7) FROM transactions")}


def _shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def payslip_vs_bank(conn) -> list[Finding]:
    """Each payslip's net pay must arrive in the bank to the cent, within about ten days of the end of its month."""
    out = []
    covered = _months_with_transactions(conn)
    for p in conn.execute("SELECT name, period, net_minor FROM payslips WHERE period<>'' ORDER BY period"):
        year, month = int(p["period"][:4]), int(p["period"][5:7])
        start = date(year, month, 1).isoformat()
        end = _shift((date(year + (month == 12), month % 12 + 1, 1)).isoformat(), 10)
        hit = conn.execute(
            "SELECT 1 FROM transactions WHERE kind='income' AND amount_minor=? AND day>=? AND day<=? AND event_id IS NULL", (p["net_minor"], start, end)
        ).fetchone()
        if hit:
            out.append(Finding("payslip ↔ bank", "ok", p["name"], f"net pay {p['net_minor'] / 100:.2f} for {p['period']} arrived in the bank"))
        elif p["period"] in covered:
            out.append(Finding("payslip ↔ bank", "warn", p["name"], f"net pay {p['net_minor'] / 100:.2f} for {p['period']} was not found as a deposit"))
    return out


def documents_vs_bank(conn) -> list[Finding]:
    """An invoice or receipt total should appear as a payment of exactly that amount, from a few days before its date to two months after."""
    out = []
    covered = _months_with_transactions(conn)
    for d in conn.execute(
        "SELECT name, kind, party, doc_date, total_minor FROM finance_docs WHERE kind IN ('invoice','receipt','ticket','booking') AND total_minor IS NOT NULL AND doc_date IS NOT NULL"
    ):
        hit = conn.execute(
            "SELECT 1 FROM transactions WHERE kind='expense' AND amount_minor=? AND day>=? AND day<=?",
            (d["total_minor"], _shift(d["doc_date"], -5), _shift(d["doc_date"], 60)),
        ).fetchone()
        label = f"{d['kind']} {d['party'] or d['name']}"
        if hit:
            out.append(Finding("document ↔ bank", "ok", d["name"], f"{label}: a payment of {d['total_minor'] / 100:.2f} was found"))
        elif d["doc_date"][:7] in covered:
            out.append(Finding("document ↔ bank", "warn", d["name"], f"{label}: no payment of {d['total_minor'] / 100:.2f} was found"))
    return out


def continuity(conn) -> list[Finding]:
    """Per account, each statement must start where the previous one ended, with no month missing."""
    out = []
    accounts = {
        r[0] for r in conn.execute("SELECT DISTINCT account FROM statement_files WHERE account<>'' AND period_start IS NOT NULL AND status<>'needs_check'")
    }
    for acc in sorted(accounts):
        files = list(
            conn.execute(
                "SELECT name, period_start, period_end, opening_minor, closing_minor FROM statement_files WHERE account=? AND period_start IS NOT NULL AND status<>'needs_check' ORDER BY period_start",
                (acc,),
            )
        )
        for a, b in itertools.pairwise(files):
            gap = (date.fromisoformat(b["period_start"]) - date.fromisoformat(a["period_end"])).days
            if gap > 5:
                out.append(Finding("continuity", "warn", acc, f"no statement between {a['period_end']} and {b['period_start']}"))
            elif a["closing_minor"] is not None and b["opening_minor"] is not None:
                same = a["closing_minor"] == b["opening_minor"]
                out.append(
                    Finding(
                        "continuity",
                        "ok" if same else "fail",
                        acc,
                        f"{a['name']} → {b['name']}: "
                        + (
                            "the balances join up"
                            if same
                            else f"closing {a['closing_minor'] / 100:.2f} does not match the next opening {b['opening_minor'] / 100:.2f}"
                        ),
                    )
                )
    return out


def plausibility(conn, today: date | None = None) -> list[Finding]:
    """Dates in the future, or a payment dated outside the statement it came from, are impossible."""
    today = today or clock.today()
    out = []
    n = conn.execute("SELECT COUNT(*) FROM transactions WHERE day>?", (today.isoformat(),)).fetchone()[0]
    out.append(
        Finding("plausibility", "fail", "payments", f"{n} payment(s) are dated in the future")
        if n
        else Finding("plausibility", "ok", "payments", "no payment is dated in the future")
    )
    for f in conn.execute("SELECT name, period_start, period_end FROM statement_files WHERE period_start IS NOT NULL AND status<>'needs_check'"):
        bad = conn.execute("SELECT COUNT(*) FROM transactions WHERE source=? AND (day<? OR day>?)", (f["name"], f["period_start"], f["period_end"])).fetchone()[
            0
        ]
        if bad:
            out.append(Finding("plausibility", "fail", f["name"], f"{bad} payment(s) are dated outside this statement's own period"))
    return out


def _main_currency(conn) -> str:
    from .db import get_setting

    return get_setting(conn, "currency", "EUR")


def _normal(account: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", account or "").upper()


def link_transfers(conn) -> list[Finding]:
    """Money moved between your OWN accounts leaves one and arrives in the other: the two payments are matched exactly (same amount, same currency,
    opposite directions, different accounts, within three days, and each the other's only candidate) and kept out of spending and income on both sides."""
    main = _main_currency(conn)
    rows = list(
        conn.execute(
            "SELECT id, day, amount_minor, kind, account, COALESCE(NULLIF(currency,''), ?) AS cur FROM transactions WHERE account<>'' AND transfer_id IS NULL AND event_id IS NULL",
            (main,),
        )
    )
    groups: dict[tuple, tuple[list, list]] = {}
    for r in rows:
        groups.setdefault((r["cur"], r["amount_minor"]), ([], []))[0 if r["kind"] == "expense" else 1].append(r)

    def gap(a, b):
        return abs((date.fromisoformat(a["day"]) - date.fromisoformat(b["day"])).days)

    paired = ambiguous = 0
    for outs, ins in groups.values():
        near_out = {o["id"]: [i for i in ins if i["account"] != o["account"] and gap(o, i) <= 3] for o in outs}
        near_in = {i["id"]: [o for o in outs if o["account"] != i["account"] and gap(o, i) <= 3] for i in ins}
        for o in outs:
            c = near_out[o["id"]]
            if len(c) == 1 and len(near_in[c[0]["id"]]) == 1:
                conn.execute("UPDATE transactions SET transfer_id=?, category='transfers', auto=1 WHERE id IN (?,?)", (o["id"], o["id"], c[0]["id"]))
                paired += 1
            elif c:
                ambiguous += 1
    conn.commit()
    cost, fx_pairs = _link_across_currencies(conn, main)
    out = []
    total = conn.execute("SELECT COUNT(*) FROM transactions WHERE transfer_id IS NOT NULL").fetchone()[0] // 2
    if total:
        out.append(
            Finding(
                "transfers",
                "ok",
                "own accounts",
                f"{total} transfer(s) between your own accounts are matched, and kept out of spending and income on both sides",
            )
        )
    if fx_pairs:
        out.append(
            Finding(
                "transfers",
                "ok",
                "currency conversion",
                f"{fx_pairs} transfer(s) between currencies matched; the conversion cost (fee + spread against the day's reference rate) is {cost / 100:.2f} EUR",
            )
        )
    if ambiguous:
        out.append(
            Finding("transfers", "warn", "own accounts", f"{ambiguous} possible transfer(s) have more than one candidate and were left as ordinary payments")
        )
    lone = conn.execute("SELECT COUNT(*) FROM transactions WHERE category='transfers' AND transfer_id IS NULL AND account<>''").fetchone()[0]
    if lone:
        out.append(
            Finding(
                "transfers",
                "warn",
                "own accounts",
                f"{lone} payment(s) look like transfers but have no matching payment in another imported account (import that account's statement)",
            )
        )
    return out


def _link_across_currencies(conn, main: str, tolerance: float = 0.06) -> tuple[int, int]:
    """Money sent from an account in one currency and received in another: the euro values must be close (a fee and a spread explain the gap), the days
    within three, and each the other's only candidate. The cost = what was sent, valued at the day's reference rate, minus what arrived, becomes an
    expense of its own ('currency conversion cost'), so the euros still tally."""
    rows = list(
        conn.execute(
            "SELECT id, day, amount_minor, kind, account, eur_minor, COALESCE(NULLIF(currency,''), ?) AS cur FROM transactions "
            "WHERE account<>'' AND transfer_id IS NULL AND event_id IS NULL AND eur_minor IS NOT NULL AND source<>'derived'",
            (main,),
        )
    )
    outs = [r for r in rows if r["kind"] == "expense"]
    ins = [r for r in rows if r["kind"] == "income"]

    def gap(a, b):
        return abs((date.fromisoformat(a["day"]) - date.fromisoformat(b["day"])).days)

    def near(o, i):
        return (
            o["cur"] != i["cur"]
            and o["account"] != i["account"]
            and gap(o, i) <= 3
            and abs(o["eur_minor"] - i["eur_minor"]) <= tolerance * max(o["eur_minor"], i["eur_minor"])
        )

    total_cost, pairs = 0, 0
    for o in outs:
        c = [i for i in ins if near(o, i)]
        if len(c) == 1 and len([x for x in outs if near(x, c[0])]) == 1:
            i = c[0]
            cost = o["eur_minor"] - i["eur_minor"]
            conn.execute("UPDATE transactions SET transfer_id=?, category='transfers', auto=1 WHERE id IN (?,?)", (o["id"], o["id"], i["id"]))
            if i["cur"] == "EUR":  # the real rate the money moved at: units of the sent currency per euro received
                conn.execute("UPDATE transactions SET rate=?, rate_source='transfer' WHERE id=?", (f"{o['amount_minor'] / i['amount_minor']:.4f}", o["id"]))
            if cost:
                conn.execute(
                    "INSERT OR IGNORE INTO transactions (day, amount_minor, kind, category, note, ref, source, auto, currency, account, eur_minor, rate, rate_source) "
                    "VALUES (?,?,?,?,?,?,'derived',1,'EUR',?,?,'1','transfer')",
                    (
                        o["day"],
                        abs(cost),
                        "expense" if cost > 0 else "income",
                        "fees" if cost > 0 else "income",
                        "Currency conversion cost (fee and spread)" if cost > 0 else "Currency conversion gain",
                        f"fx:{o['id']}:{i['id']}",
                        o["account"],
                        abs(cost),
                    ),
                )
            total_cost += cost
            pairs += 1
    conn.commit()
    return total_cost, pairs


def conversion(conn) -> list[Finding]:
    """Every payment that is not in euros must have been converted at the rate of its own day, and say so; one without a rate is reported, never guessed."""
    main = _main_currency(conn)
    out = []
    for cur in [r[0] for r in conn.execute("SELECT DISTINCT COALESCE(NULLIF(currency,''), ?) FROM transactions", (main,)) if r[0] != "EUR"]:
        done, missing = conn.execute(
            "SELECT SUM(eur_minor IS NOT NULL), SUM(eur_minor IS NULL) FROM transactions WHERE COALESCE(NULLIF(currency,''), ?) = ?", (main, cur)
        ).fetchone()
        if done:
            out.append(Finding("conversion", "ok", cur, f"{done} payment(s) in {cur} converted to euros at the ECB reference rate of their own day"))
        if missing:
            out.append(
                Finding(
                    "conversion",
                    "warn",
                    cur,
                    f"{missing} payment(s) in {cur} have no exchange rate for their day, so they are left out of the euro totals (run ./scripts/fetch-rates.sh on your Mac, then Read my files)",
                )
            )
    return out


def account_ledger(conn) -> list[Finding]:
    """For each run of consecutive, proven statements of an account: opening balance + ALL payments stored for that account in that time = closing balance.
    This is what catches a payment lost, or counted twice, between the statement and your ledger."""
    out = []
    for acc in [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT account FROM statement_files WHERE account<>'' AND status='verified' AND opening_minor IS NOT NULL AND closing_minor IS NOT NULL"
        )
    ]:
        files = list(
            conn.execute(
                "SELECT name, period_start, period_end, opening_minor, closing_minor FROM statement_files WHERE account=? AND status='verified' "
                "AND opening_minor IS NOT NULL AND closing_minor IS NOT NULL AND period_start IS NOT NULL ORDER BY period_start",
                (acc,),
            )
        )
        chains: list[list] = []
        for f in files:
            if (
                chains
                and chains[-1][-1]["closing_minor"] == f["opening_minor"]
                and (date.fromisoformat(f["period_start"]) - date.fromisoformat(chains[-1][-1]["period_end"])).days <= 5
            ):
                chains[-1].append(f)
            else:
                chains.append([f])
        for chain in chains:
            start, end = chain[0]["period_start"], chain[-1]["period_end"]
            actual = conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN kind='income' THEN amount_minor ELSE -amount_minor END), 0) FROM transactions WHERE account=? AND day>=? AND day<=?",
                (_normal(acc), start, end),
            ).fetchone()[0]
            expected = chain[-1]["closing_minor"] - chain[0]["opening_minor"]
            label = f"{acc} {start} to {end}"
            out.append(
                Finding("account ledger", "ok", label, f"opening + the {len(chain)} statement(s)' payments = closing ({expected / 100:.2f})")
                if actual == expected
                else Finding(
                    "account ledger",
                    "fail",
                    label,
                    f"the stored payments add up to {actual / 100:.2f} but the statements say {expected / 100:.2f} (difference {(actual - expected) / 100:.2f})",
                )
            )
    return out


def label_of(cur: str) -> str:
    return "all in EUR" if cur == "ALL" else cur


def _shown(conn, m: str) -> int:
    """What the reports show for a month, in minor units: money in minus everything spent."""
    from .modules import events, money

    return round(money.income_summary(conn, {"month": m})["total"] * 100) - sum(round(x["net"] * 100) for x in events.spending_by_main(conn, {"month": m}))


def tally_month(conn, m: str) -> str | None:
    """Right now, in the view in use: do the reports for month `m` equal the raw ledger (plus transfers between your own accounts)? None if yes, else why not."""
    net = "COALESCE(SUM(CASE WHEN kind='income' THEN amount_minor ELSE -amount_minor END),0)"
    raw = conn.execute(f"SELECT {net} FROM ledger WHERE day>=? AND day<?", (m + "-01", _next_month(m))).fetchone()[0]
    tr = conn.execute(f"SELECT {net} FROM ledger WHERE day>=? AND day<? AND category='transfers' AND event_id IS NULL", (m + "-01", _next_month(m))).fetchone()[
        0
    ]
    shown = _shown(conn, m)
    return None if raw == shown + tr else f"the ledger's net change is {raw / 100:.2f} but the reports plus transfers give {(shown + tr) / 100:.2f}"


def _next_month(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y + (mo == 12)}-{mo % 12 + 1:02d}-01"


def tally(conn) -> list[Finding]:
    """Every month, in every currency: the net cash change in the raw ledger must equal what the reports show (money in - day to day - trips and events)
    plus the transfers between your own accounts. If any report drops or double-counts a payment, this fails."""
    from . import db

    original = db.get_setting(conn, "view_currency", "")
    main = _main_currency(conn)
    out = []
    try:
        for cur in ["ALL", *[r[0] for r in conn.execute("SELECT DISTINCT COALESCE(NULLIF(currency,''), ?) FROM transactions", (main,))]]:
            db.set_setting(conn, "view_currency", cur)
            db.ledger_view(conn)
            net = "COALESCE(SUM(CASE WHEN kind='income' THEN amount_minor ELSE -amount_minor END),0)"
            raws = {r[0]: r[1] for r in conn.execute(f"SELECT substr(day,1,7), {net} FROM ledger GROUP BY 1 ORDER BY 1")}  # one pass, not one per month
            trs = {r[0]: r[1] for r in conn.execute(f"SELECT substr(day,1,7), {net} FROM ledger WHERE category='transfers' AND event_id IS NULL GROUP BY 1")}
            months = list(raws)
            bad = 0
            for m in months:
                raw, tr = raws[m], trs.get(m, 0)
                shown = _shown(conn, m)
                if raw != shown + tr:
                    bad += 1
                    out.append(
                        Finding(
                            "tally",
                            "fail",
                            f"{label_of(cur)} {m}",
                            f"the ledger's net change is {raw / 100:.2f} but the reports plus transfers give {(shown + tr) / 100:.2f}",
                        )
                    )
            label = "all in EUR" if cur == "ALL" else cur
            if months and not bad:
                out.append(
                    Finding(
                        "tally",
                        "ok",
                        label,
                        f"{len(months)} month(s) {'in euros (everything converted)' if cur == 'ALL' else 'in ' + cur}: the reports and the raw ledger agree to the cent",
                    )
                )
    finally:
        db.set_setting(conn, "view_currency", original) if original else conn.execute("DELETE FROM settings WHERE key='view_currency'")
        conn.commit()
        db.ledger_view(conn)
    return out


def currency_mix(conn) -> list[Finding]:
    main = _main_currency(conn)
    found = [r[0] for r in conn.execute("SELECT DISTINCT COALESCE(NULLIF(currency,''), ?) FROM transactions", (main,))]
    return (
        [Finding("currency", "ok", "payments", f"payments are in {', '.join(sorted(found))}: totals are always shown one currency at a time")]
        if len(found) > 1
        else []
    )


CROSS_AGENTS = (link_transfers, conversion, payslip_vs_bank, documents_vs_bank, continuity, account_ledger, tally, plausibility, currency_mix)


def run_cross_checks(conn) -> list[Finding]:
    """Run every cross-document agent and store the findings (the previous cross-document findings are replaced)."""
    from . import insight, notes_check

    found = [f for agent in (*CROSS_AGENTS, notes_check.notes_arithmetic, notes_check.notes_vs_app, *insight.EXTRA_AGENTS) for f in agent(conn)]
    conn.execute("DELETE FROM findings WHERE cross=1")
    conn.executemany(
        "INSERT INTO findings (agent, level, subject, message, cross) VALUES (?,?,?,?,1)", [(f.agent, f.level, f.subject, f.message) for f in found]
    )
    conn.commit()
    return found


def store_file_findings(conn, subject: str, findings: list[Finding]) -> None:
    conn.execute("DELETE FROM findings WHERE cross=0 AND subject=?", (subject,))
    conn.executemany(
        "INSERT INTO findings (agent, level, subject, message, cross) VALUES (?,?,?,?,0)", [(f.agent, f.level, f.subject, f.message) for f in findings]
    )
    conn.commit()


# ---- the agent register: what exists, what is proposed -------------------------------------------------------------------------
# status: built = running today; planned = designed, not built. Independent agents can run side by side; today the cross-document agents run one after
# another in about a second, and the file readers wait on the single local model.
AGENTS: list[dict[str, str]] = [
    # getting information out of any file
    {
        "group": "Reading files",
        "name": "File reader",
        "does": "PDF, scans, photos, spreadsheets, Word, web pages, emails, JSON, ZIP all become the same plain shape",
        "status": "built",
    },
    {"group": "Reading files", "name": "OCR reader", "does": "Reads scanned PDFs and photos offline (Dutch + English) with word positions", "status": "built"},
    {"group": "Reading files", "name": "Unlocker", "does": "Opens password-protected PDFs with the passwords you list in passwords.txt", "status": "built"},
    {"group": "Reading files", "name": "Archive and email opener", "does": "Opens ZIPs and emails, one file at a time, bounded", "status": "built"},
    {
        "group": "Reading files",
        "name": "OCR confidence guard",
        "does": "Re-reads low-confidence scan pages at higher resolution and flags digits it is unsure of",
        "status": "planned",
    },
    {"group": "Reading files", "name": "Second OCR engine", "does": "Reads scans with two engines and compares every figure", "status": "planned"},
    {
        "group": "Reading files",
        "name": "Handwriting and receipt photo reader",
        "does": "A stronger on-device vision model for crumpled receipts and handwriting",
        "status": "planned",
    },
    # turning a statement into transactions
    {"group": "Reading statements", "name": "Standard reader", "does": "MT940 and camt.053 exactly, no model", "status": "built"},
    {
        "group": "Reading statements",
        "name": "Layout reader",
        "does": "The local model only says which column is which; code reads every figure",
        "status": "built",
    },
    {
        "group": "Reading statements",
        "name": "Second reader",
        "does": "Works the layout out again from another part of the file; both readings must agree",
        "status": "built",
    },
    {
        "group": "Reading statements",
        "name": "Third reader (majority vote)",
        "does": "A third independent reading; two of three must agree",
        "status": "planned",
    },
    {"group": "Reading statements", "name": "Currency detector", "does": "Which currency a statement is in, from what it prints", "status": "built"},
    # proving the numbers
    {
        "group": "Proving the numbers",
        "name": "Balance prover",
        "does": "Running balances add up, line by line, oldest-first or newest-first",
        "status": "built",
    },
    {"group": "Proving the numbers", "name": "Totals prover", "does": "Opening + transactions = closing; also proves credit cards", "status": "built"},
    {"group": "Proving the numbers", "name": "Account ledger", "does": "Statements vs the payments stored for the account", "status": "built"},
    {"group": "Proving the numbers", "name": "Continuity", "does": "Each statement starts where the last ended; no month missing", "status": "built"},
    {"group": "Proving the numbers", "name": "Tally", "does": "The reports equal the raw ledger every month, in euros and per currency", "status": "built"},
    {"group": "Proving the numbers", "name": "Plausibility", "does": "Nothing dated in the future or outside its statement", "status": "built"},
    {
        "group": "Proving the numbers",
        "name": "Self-test canary",
        "does": "Runs known sample statements through the readers at every start and fails loudly if anything changed",
        "status": "built",
    },
    {"group": "Proving the numbers", "name": "Audit log", "does": "An unchangeable record of every import and correction", "status": "built"},
    # money in euros
    {"group": "Euros", "name": "Converter", "does": "Every payment in euros at the ECB reference rate of its own day", "status": "built"},
    {"group": "Euros", "name": "Transfer matcher", "does": "Pairs money moved between your own accounts, in one currency or two", "status": "built"},
    {"group": "Euros", "name": "Conversion-cost agent", "does": "Fee and spread of a currency transfer, booked as its own expense", "status": "built"},
    {
        "group": "Euros",
        "name": "Statement-rate agent",
        "does": "Uses the rate and fee printed on a statement or Wise CSV instead of the reference rate",
        "status": "planned",
    },
    {"group": "Euros", "name": "Rate freshness agent", "does": "Warns when the rate file is out of date", "status": "built"},
    # comparing documents with each other
    {"group": "Cross-checking documents", "name": "Payslip <-> bank", "does": "Net pay arrives in the bank to the cent", "status": "built"},
    {
        "group": "Cross-checking documents",
        "name": "Invoice/receipt <-> bank",
        "does": "Every invoice and receipt total appears as a payment",
        "status": "built",
    },
    {"group": "Cross-checking documents", "name": "Notes arithmetic", "does": "Your calculations in Apple Notes add up", "status": "built"},
    {"group": "Cross-checking documents", "name": "Notes <-> app", "does": "Your notes agree with the app, line by line", "status": "built"},
    {"group": "Cross-checking documents", "name": "Tax letter agent", "does": "Tax assessments and refunds vs payments", "status": "built"},
    {"group": "Cross-checking documents", "name": "Insurance and contract agent", "does": "Premiums and rent vs what was actually paid", "status": "built"},
    {
        "group": "Cross-checking documents",
        "name": "Year-end agent",
        "does": "Your annual income statement (jaaropgave) vs twelve payslips and the bank",
        "status": "built",
    },
    {"group": "Cross-checking documents", "name": "VAT agent", "does": "Adds up the VAT on invoices and receipts", "status": "built"},
    {"group": "Cross-checking documents", "name": "Refund matcher", "does": "Ties each refund to its original purchase", "status": "built"},
    # understanding
    {"group": "Understanding", "name": "Categoriser", "does": "Rules, then the local model, then your corrections", "status": "built"},
    {"group": "Understanding", "name": "Event grouper", "does": "Groups tickets, flights, stays and refunds into trips, matches and shows", "status": "built"},
    {"group": "Understanding", "name": "Merchant normaliser", "does": "Treats 'AH 1234' and 'Albert Heijn' as one shop", "status": "built"},
    {"group": "Understanding", "name": "Duplicate-payment agent", "does": "Spots the same payment charged twice", "status": "built"},
    {"group": "Understanding", "name": "Price-change agent", "does": "Tells you when a regular bill or subscription changes", "status": "built"},
    {"group": "Understanding", "name": "Unusual-payment agent", "does": "Flags payments that do not fit your pattern", "status": "built"},
    {"group": "Understanding", "name": "Net-worth agent", "does": "All account balances in euros, over time", "status": "built"},
    {"group": "Understanding", "name": "Forecast agent", "does": "Upcoming regular payments and what is left", "status": "built"},
    # safety
    {
        "group": "Safety",
        "name": "Privacy sentinel",
        "does": "Nothing in the app can use the network; the model and the data stay on this Mac",
        "status": "built",
    },
    {"group": "Safety", "name": "Backup and integrity agent", "does": "Encrypted backup of the database and a check that it is intact", "status": "built"},
]
