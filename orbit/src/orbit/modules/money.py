"""Income, expenses and monthly category budgets. Amounts are stored as integer minor units (paise/cents)."""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from datetime import date

from .. import categorize, dates, extract, payslips, rates, standards, statements, verify
from ..db import get_setting, rows
from ..module import Module, N, S, Tool

MIGRATIONS = (
    """
    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY,
        day TEXT NOT NULL,
        amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
        kind TEXT NOT NULL CHECK (kind IN ('expense','income')),
        category TEXT NOT NULL DEFAULT 'other',
        note TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX tx_day ON transactions(day);
    CREATE TABLE budgets (category TEXT PRIMARY KEY, monthly_minor INTEGER NOT NULL);
    """,
    """
    ALTER TABLE transactions ADD COLUMN ref TEXT;                          -- stable id of an imported line: the same line is never added twice
    ALTER TABLE transactions ADD COLUMN source TEXT NOT NULL DEFAULT '';   -- the statement it came from
    ALTER TABLE transactions ADD COLUMN balance_minor INTEGER;
    ALTER TABLE transactions ADD COLUMN auto INTEGER NOT NULL DEFAULT 0;   -- 1 = category chosen by rules/model, 0 = chosen by you
    CREATE UNIQUE INDEX tx_ref ON transactions(ref) WHERE ref IS NOT NULL;
    CREATE TABLE merchant_rules (merchant TEXT PRIMARY KEY, category TEXT NOT NULL);
    CREATE TABLE payslips (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, period TEXT NOT NULL, gross_minor INTEGER NOT NULL, net_minor INTEGER NOT NULL,
        tax_minor INTEGER, pension_minor INTEGER, holiday_minor INTEGER
    );
    CREATE TABLE statement_files (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, found INTEGER NOT NULL, added INTEGER NOT NULL,
        at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    -- what the model read from every finance file: invoices, receipts, tax, insurance ... (a new step: existing databases get it too)
    CREATE TABLE IF NOT EXISTS finance_docs (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
        party TEXT NOT NULL DEFAULT '', doc_date TEXT, due_date TEXT, reference TEXT NOT NULL DEFAULT '',
        total_minor INTEGER, vat_minor INTEGER, currency TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS finance_docs_kind ON finance_docs(kind, doc_date);
    """,
    """
    ALTER TABLE statement_files ADD COLUMN status TEXT NOT NULL DEFAULT 'ok';      -- verified | unverified | needs_check | ok (not a statement)
    ALTER TABLE statement_files ADD COLUMN issues TEXT NOT NULL DEFAULT '';        -- why a file needs a check
    """,
    """
    ALTER TABLE statement_files ADD COLUMN account TEXT NOT NULL DEFAULT '';       -- the account/card number printed on the statement
    ALTER TABLE statement_files ADD COLUMN period_start TEXT;
    ALTER TABLE statement_files ADD COLUMN period_end TEXT;
    ALTER TABLE statement_files ADD COLUMN opening_minor INTEGER;
    ALTER TABLE statement_files ADD COLUMN closing_minor INTEGER;
    ALTER TABLE statement_files ADD COLUMN proofs TEXT NOT NULL DEFAULT '';        -- how it was proved
    CREATE TABLE findings (                                                        -- what each verifier agent concluded
        id INTEGER PRIMARY KEY, agent TEXT NOT NULL, level TEXT NOT NULL CHECK (level IN ('ok','warn','fail')),
        subject TEXT NOT NULL, message TEXT NOT NULL, cross INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT '';        -- '' = the main currency
    ALTER TABLE transactions ADD COLUMN account TEXT NOT NULL DEFAULT '';         -- the account/card the payment belongs to, as printed on its statement
    ALTER TABLE transactions ADD COLUMN transfer_id INTEGER;                      -- the other half of a transfer between your own accounts
    ALTER TABLE statement_files ADD COLUMN currency TEXT NOT NULL DEFAULT '';
    CREATE INDEX tx_account ON transactions(account, day);
    """,
    """
    ALTER TABLE transactions ADD COLUMN eur_minor INTEGER;                        -- the amount in euros at the rate of its own day (NULL = not converted yet)
    ALTER TABLE transactions ADD COLUMN rate TEXT NOT NULL DEFAULT '';            -- units of the payment's currency per 1 EUR that were used
    ALTER TABLE transactions ADD COLUMN rate_source TEXT NOT NULL DEFAULT '';     -- 'euro' | 'ecb <day>' | 'transfer'
    CREATE TABLE rates (day TEXT NOT NULL, currency TEXT NOT NULL, per_eur TEXT NOT NULL, PRIMARY KEY (day, currency));
    """,
)


def to_minor(x: float) -> int:
    return round(float(x) * 100)


def currency(conn) -> str:
    return get_setting(conn, "currency", "EUR")


def add_transaction(conn, a):
    amt = to_minor(a["amount"])
    if amt <= 0:
        raise ValueError("amount must be positive")
    day = a.get("date") or date.today().isoformat()
    dates.parse(day)
    cur = conn.execute(
        "INSERT INTO transactions (day, amount_minor, kind, category, note) VALUES (?,?,?,?,?)",
        (day, amt, a.get("kind", "expense"), a.get("category", "other").strip().lower(), a.get("note", "")),
    )
    conn.commit()
    return {"id": cur.lastrowid, "amount": amt / 100, "currency": currency(conn), "date": day}


def list_transactions(conn, a):
    where, args = [], []
    for col, op, key in (("t.day", ">=", "since"), ("t.day", "<=", "until")):
        if a.get(key):
            where.append(f"{col} {op} ?")
            args.append(a[key])
    if a.get("category"):
        where.append("t.category=?")
        args.append(a["category"].lower())
    sql = ("SELECT t.id, t.day, t.kind, t.category, t.note, t.amount_minor/100.0 AS amount, t.native_minor/100.0 AS original, "
           "COALESCE(NULLIF(t.currency,''), (SELECT COALESCE((SELECT value FROM settings WHERE key='currency'),'EUR'))) AS currency, t.event_id, t.sub, e.name AS event "
           "FROM ledger t LEFT JOIN events e ON e.id=t.event_id")
    sql += " WHERE " + " AND ".join(where) if where else ""
    return rows(conn.execute(sql + " ORDER BY t.day DESC, t.id DESC LIMIT ?", [*args, int(a.get("limit", 50))]))


def summary(conn, a):
    start, end = dates.month_bounds(a.get("month") or date.today().strftime("%Y-%m"))
    by_cat = rows(conn.execute(
        "SELECT category, SUM(amount_minor)/100.0 AS spent FROM ledger "
        "WHERE kind='expense' AND category<>'transfers' AND day>=? AND day<? GROUP BY category ORDER BY spent DESC", (start, end)))
    tot = {r["kind"]: r["t"] for r in conn.execute(
        "SELECT kind, SUM(amount_minor)/100.0 AS t FROM ledger WHERE category<>'transfers' AND NOT (kind='income' AND event_id IS NOT NULL) "
        "AND day>=? AND day<? GROUP BY kind",
        (start, end))}
    budgets = {r["category"]: r["monthly_minor"] / 100 for r in conn.execute("SELECT * FROM budgets")}
    for r in by_cat:
        if r["category"] in budgets:
            r["budget"], r["left"] = budgets[r["category"]], budgets[r["category"]] - r["spent"]
    return {"month": start[:7], "currency": currency(conn), "spent": tot.get("expense", 0),
            "income": tot.get("income", 0), "net": tot.get("income", 0) - tot.get("expense", 0),
            "by_category": by_cat}


INCOME_NAMES = {"income": "other income", "refund": "refunds", "interest": "interest"}


def income_summary(conn, a=None):
    """Money in for a month, by source (salary, interest, refunds, other), with the month before and the payslip figures if there is one.
    Refunds that belong to a trip or event are not income: they are netted inside that event."""
    from datetime import date

    a = a or {}
    month = a.get("month") or date.today().strftime("%Y-%m")
    start, end = dates.month_bounds(month)
    before_start = dates.add_months(date.fromisoformat(start), -1).isoformat()

    def by_source(lo, hi):
        out: dict[str, list] = {}
        for r in conn.execute("SELECT category, note, amount_minor FROM ledger WHERE kind='income' AND event_id IS NULL AND category<>'transfers' AND day>=? AND day<?", (lo, hi)):
            name = INCOME_NAMES.get(r["category"], r["category"])  # salary stays 'salary': its description carries the month, so it would never match last month's
            slot = out.setdefault(name, [0, 0])
            slot[0] += r["amount_minor"]
            slot[1] += 1
        return out

    now, before = by_source(start, end), by_source(before_start, start)
    sources = sorted(({"source": k, "amount": v[0] / 100, "payments": v[1], "before": before.get(k, [0])[0] / 100} for k, v in now.items()), key=lambda x: -x["amount"])
    slip = conn.execute("SELECT period, gross_minor/100.0 AS gross, tax_minor/100.0 AS tax, pension_minor/100.0 AS pension, holiday_minor/100.0 AS holiday, net_minor/100.0 AS net "
                        "FROM payslips WHERE period=? ORDER BY name LIMIT 1", (month,)).fetchone()
    return {"month": month, "total": round(sum(s["amount"] for s in sources), 2), "before": round(sum(v[0] for v in before.values()) / 100, 2),
            "sources": sources, "payslip": dict(slip) if slip else None}


def set_budget(conn, a):
    conn.execute("INSERT OR REPLACE INTO budgets VALUES (?,?)", (a["category"].strip().lower(), to_minor(a["monthly_amount"])))
    conn.commit()
    return {"category": a["category"].lower(), "monthly_amount": a["monthly_amount"]}


def delete_transaction(conn, a):
    conn.execute("DELETE FROM transactions WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


# ---- statements -------------------------------------------------------------------------------------------------------
def _store(conn, d, txns, learned, account: str = "", currency: str = "") -> int:
    new = 0
    scope = re.sub(r"[^A-Za-z0-9]", "", account).upper()
    for ref, t in statements.with_references(txns, scope):
        cur = conn.execute(
            "INSERT OR IGNORE INTO transactions (day, amount_minor, kind, category, note, ref, source, balance_minor, auto, currency, account) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (t.day, t.amount_minor, t.kind, categorize.categorise(t.desc, t.kind, learned), t.desc[:300], ref, d["name"][:200], t.balance_minor, currency, scope))
        new += cur.rowcount
    conn.commit()
    return new


def _day(value) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def _money(value) -> int | None:
    return round(abs(float(value)) * 100) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _remember_doc(conn, d, info) -> None:
    """Keep what the model read from a finance file: what it is, who it is from, when, how much."""
    conn.execute("INSERT OR REPLACE INTO finance_docs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (d["sha256"], d["name"], info.get("kind", "other"), str(info.get("title") or "")[:120], str(info.get("summary") or "")[:300],
                  str(info.get("party") or "")[:120], _day(info.get("date")), _day(info.get("due_date")), str(info.get("reference") or "")[:60],
                  _money(info.get("total")), _money(info.get("vat")), str(info.get("currency") or "")[:5].upper()))


def finance_documents(conn, a=None):
    """Finance files by what they are (invoice, receipt, payslip, tax, insurance, contract ...) with who/when/how much."""
    a = a or {}
    where, args = [], []
    for key, col in (("kind", "kind"),):
        if a.get(key):
            where.append(f"{col}=?")
            args.append(a[key])
    if a.get("party"):
        where.append("(party LIKE ? OR title LIKE ? OR name LIKE ?)")
        args += [f"%{a['party']}%"] * 3
    for key, op in (("since", ">="), ("until", "<=")):
        if a.get(key):
            where.append(f"doc_date {op} ?")
            args.append(a[key])
    sql = ("SELECT kind, title, party, doc_date AS date, due_date, reference, total_minor/100.0 AS total, vat_minor/100.0 AS vat, currency, summary, name "
           "FROM finance_docs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY doc_date DESC, name LIMIT ?")
    return rows(conn.execute(sql, [*args, int(a.get("limit", 50))]))


def finance_document_totals(conn, a=None):
    """Totals of invoices / receipts / insurance ... by kind, month or who it is from."""
    a = a or {}
    group = {"month": "substr(doc_date,1,7)", "party": "party", "kind": "kind"}.get(a.get("by", "kind"), "kind")
    where, args = ["total_minor IS NOT NULL", "kind NOT IN ('bank_statement','payslip')"], []
    if a.get("kind"):
        where.append("kind=?")
        args.append(a["kind"])
    for key, op in (("since", ">="), ("until", "<=")):
        if a.get(key):
            where.append(f"doc_date {op} ?")
            args.append(a[key])
    return rows(conn.execute(f"SELECT {group} AS grp, COUNT(*) AS documents, SUM(total_minor)/100.0 AS total, SUM(COALESCE(vat_minor,0))/100.0 AS vat "
                             f"FROM finance_docs WHERE {' AND '.join(where)} GROUP BY grp ORDER BY total DESC LIMIT 50", args))


def _read_standard(kind: str, text: str, name: str) -> verify.Read:
    """MT940 / camt.053: exact formats, no model needed."""
    statements_ = standards.read_mt940(text) if kind == "mt940" else standards.read_camt(text)
    r = verify.Read()
    for s in statements_:
        r.txns += s.txns
        r.issues += s.issues
    r.account = statements_[0].account if statements_ else ""
    r.currency = next((s.currency for s in statements_ if s.currency), "")
    if r.txns:
        days = sorted(t.day for t in r.txns)
        r.first, r.last = days[0], days[-1]
    if len(statements_) == 1:
        r.opening, r.closing = statements_[0].opening, statements_[0].closing
    proven = bool(statements_) and all(s.status == "verified" for s in statements_)
    r.proofs = ["opening + transactions = closing"] if proven else []
    r.status = "needs_check" if r.issues else ("verified" if proven else "unverified")
    r.findings = [verify.Finding("standard reader", "fail" if r.issues else "ok", name,
                                 "; ".join(r.issues[:3]) if r.issues else f"{len(r.txns)} transactions; opening balance + transactions = closing balance, to the cent")]
    return r


def import_statements(conn, a=None, client=None, model=None, progress=None):
    """Read every finance document the parser has produced and not yet imported. Safe to repeat: a line is never added twice.

    Bank standards (MT940, camt.053) are read exactly, without a model. Other statements: the local model only describes the layout, code reads every
    figure, and verifier agents (balances, totals, a second independent reading) must all agree. A file that fails is not counted. Without the model,
    only the exact standards can be imported (a guess at a layout could silently give wrong numbers)."""
    learned = categorize.learned_rules(conn)
    done = {r[0] for r in conn.execute("SELECT sha256 FROM statement_files")}
    files = added = duplicates = payslip_count = 0
    empty: list[str] = []
    problems: list[str] = []
    needs_check: list[dict] = []
    docs = [d for d in conn.execute("SELECT sha256, name, kind, text, data FROM documents WHERE area='finance' ORDER BY id").fetchall() if d["sha256"] not in done]
    for index, d in enumerate(docs, 1):
        try:
            data = json.loads(d["data"]) if d["data"] else {}
        except ValueError:
            data = {}
        slip = None
        info: dict = {}
        status, issues = "ok", []
        txns: list[statements.Txn] = []
        new = 0
        rd: verify.Read | None = None
        if rates.looks_like_ecb(data.get("rows")):  # the ECB's exchange-rate file: loaded into the rates table, not a document about your money
            n = rates.store(conn, rates.parse_ecb(data["rows"]))
            _remember_doc(conn, d, {"kind": "other", "title": "ECB exchange rates"})
            conn.execute("INSERT INTO statement_files (sha256, name, found, added, status) VALUES (?,?,0,0,'ok')", (d["sha256"], d["name"]))
            verify.store_file_findings(conn, d["name"], [verify.Finding("rates", "ok", d["name"], f"{n} exchange rates loaded")])
            files += 1
            conn.commit()
            continue
        standard = standards.sniff(d["text"])
        if standard:
            info = {"kind": "bank_statement", "title": "Bank statement"}
            _remember_doc(conn, d, info)
            rd = _read_standard(standard, d["text"], d["name"])
        elif client is not None and model:
            try:
                info = extract.classify(client, model, d["name"], d["text"])
                _remember_doc(conn, d, info)
                if info["kind"] == "payslip":
                    slip = payslips.from_model(info)
                elif info["kind"] == "bank_statement":
                    if progress:
                        progress(f"{d['name']}: reading and checking ({index} of {len(docs)} files)")
                    rd = verify.read_table_statement(client, model, d["name"], data, d["text"])
            except RuntimeError as exc:  # the model could not be reached: stop, nothing is marked as done
                problems.append(str(exc))
                break
        else:
            msg = "The local model is not running, so these statements cannot be read. Start Ollama and try again."
            if msg not in problems:
                problems.append(msg)
            continue
        extra = ("", None, None, None, None, "")
        if rd is not None:
            status, issues = rd.status, rd.issues
            if status != "needs_check":  # nothing from a file that fails its own proof ever reaches your totals
                txns = rd.txns
                new = _store(conn, d, txns, learned, rd.account, rd.currency)
            else:
                needs_check.append({"file": d["name"], "issues": issues[:5]})
            verify.store_file_findings(conn, d["name"], rd.findings)
            extra = (rd.account, rd.first or None, rd.last or None, rd.opening, rd.closing, "; ".join(rd.proofs))
        if slip is not None:
            conn.execute("INSERT OR IGNORE INTO payslips VALUES (?,?,?,?,?,?,?,?)", (d["sha256"], d["name"], slip.period, slip.gross_minor, slip.net_minor,
                                                                                   slip.tax_minor, slip.pension_minor, slip.holiday_minor))
            payslip_count += 1
        conn.execute("INSERT INTO statement_files (sha256, name, found, added, status, issues, account, period_start, period_end, opening_minor, closing_minor, proofs, currency) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (d["sha256"], d["name"], len(txns), new, status, "; ".join(issues)[:500], *extra, rd.currency if rd is not None else ""))
        files += 1
        added += new
        duplicates += len(txns) - new
        if not txns and slip is None and info.get("kind") == "bank_statement" and status != "needs_check":
            empty.append(d["name"])
        conn.commit()
    rates.convert_all(conn)  # every payment in euros at the rate of its own day
    verify.run_cross_checks(conn)  # payslips vs bank, invoices vs bank, continuity, plausibility: every time, on everything
    if client is not None and model and added:  # merchants the rules could not place: the local model sees only their names
        try:
            categorize.recategorise_with_model(conn, client, model)
        except RuntimeError as exc:
            problems.append(f"Imported, but the merchants could not be sorted by the model: {exc}")
    if client is not None and model and added:  # trips, matches and shows: the model groups the payments that belong together
        try:
            from . import events

            events.suggest(conn, client, model, progress=progress)
        except RuntimeError as exc:
            problems.append(f"Imported, but the payments could not be grouped into trips and events: {exc}")
    return {"files": files, "new_transactions": added, "already_had": duplicates, "payslips": payslip_count,
            "files_with_no_transactions": empty, "needs_check": needs_check, "problems": problems}


def currencies(conn, a=None):
    """The currencies in your ledger with how many payments each has, and which one is being viewed. Totals never mix them."""
    from .. import db

    main = db.get_setting(conn, "currency", "EUR")
    out = rows(conn.execute("SELECT COALESCE(NULLIF(currency,''), ?) AS currency, COUNT(*) AS payments FROM transactions GROUP BY 1 ORDER BY payments DESC", (main,)))
    viewing = db.view_currency(conn)
    return {"viewing": viewing, "main": main, "currencies": out}


def agent_list(conn, a=None):
    """Every verifier and helper agent, grouped, with whether it is running today or only planned."""
    return {"agents": verify.AGENTS, "built": sum(1 for x in verify.AGENTS if x["status"] == "built"), "planned": sum(1 for x in verify.AGENTS if x["status"] == "planned")}


def verification_report(conn, a=None):
    """What every verifier agent concluded: counts per agent, and every warning and failure in words."""
    found = rows(conn.execute("SELECT agent, level, subject, message FROM findings ORDER BY (level='fail') DESC, (level='warn') DESC, agent, subject"))
    summary: dict[str, dict[str, int]] = {}
    for f in found:
        summary.setdefault(f["agent"], {"ok": 0, "warn": 0, "fail": 0})[f["level"]] += 1
    return {"summary": summary, "problems": [f for f in found if f["level"] != "ok"], "passed": sum(1 for f in found if f["level"] == "ok")}


def list_payslips(conn, a=None):
    """Payslips by month: gross, tax, pension, holiday pay and net, in currency units."""
    out = rows(conn.execute("SELECT period, name, gross_minor/100.0 AS gross, tax_minor/100.0 AS tax, pension_minor/100.0 AS pension, "
                            "holiday_minor/100.0 AS holiday, net_minor/100.0 AS net FROM payslips ORDER BY period DESC, name"))
    return out[: int((a or {}).get("limit", 36))]


def files_to_check(conn, a=None):
    """Statements that could not be proven correct (not imported) or could not be checked (imported, marked), with the reason."""
    return rows(conn.execute("SELECT name AS file, status, issues FROM statement_files WHERE status IN ('needs_check','unverified') ORDER BY status, name"))


def statement_report(conn, a=None):
    """For each finance file: what Orbit made of it, with no content shown. Use it to see which files could not be read."""
    out = []
    for d in conn.execute("SELECT d.name, d.kind, d.text, s.found, s.added FROM documents d LEFT JOIN statement_files s ON s.sha256=d.sha256 "
                          "WHERE d.area='finance' ORDER BY d.name"):
        slip = bool(conn.execute("SELECT 1 FROM payslips WHERE name=?", (d["name"],)).fetchone())
        out.append({"file": d["name"], "type": d["kind"], "text_characters": len(d["text"]), "payslip": slip,
                    "transactions_found": d["found"], "imported": d["added"], "read": d["found"] is not None})
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
    out = rows(conn.execute(
        "SELECT substr(day,1,7) AS month, SUM(CASE WHEN kind='expense' THEN amount_minor ELSE 0 END)/100.0 AS spent, "
        "SUM(CASE WHEN kind='income' THEN amount_minor ELSE 0 END)/100.0 AS income FROM ledger "
        "WHERE category<>'transfers' GROUP BY month ORDER BY month DESC LIMIT ?", (months,)))
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
        gaps = [(b - a_).days for a_, b in zip(days, days[1:], strict=False) if (b - a_).days > 0]
        amounts = [x for _, x in items]
        mid = statistics.median(amounts)
        if gaps and 25 <= statistics.median(gaps) <= 35 and sum(abs(x - mid) <= 0.15 * mid for x in amounts) >= 0.7 * len(amounts):
            found.append({"merchant": m, "typical_amount": round(mid / 100, 2), "times": len(items), "last": items[-1][0],
                          "per_month": round(mid / 100, 2)})
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
    return {"merchant": m, "category": a["category"].lower()}


MODULE = Module(
    "money",
    MIGRATIONS,
    (
        Tool("add_transaction", "Record an expense (default) or income. Amount is positive, in the user's currency.",
             {"amount": N("Positive amount"), "kind": S("expense or income", enum=["expense", "income"]),
              "category": S("e.g. groceries, rent, medical, travel, salary"), "note": S("What it was for"),
              "date": S("YYYY-MM-DD, default today")}, add_transaction, ("amount",)),
        Tool("list_transactions", "List transactions, newest first.",
             {"since": S("YYYY-MM-DD"), "until": S("YYYY-MM-DD"), "category": S("Category"), "limit": N("Max rows")},
             list_transactions),
        Tool("spending_summary", "Totals for a month: spent, income, net and per-category spend vs budget.",
             {"month": S("YYYY-MM, default current month")}, summary),
        Tool("set_budget", "Set a monthly budget for a category.",
             {"category": S("Category"), "monthly_amount": N("Amount per month")}, set_budget,
             ("category", "monthly_amount")),
        Tool("import_statements", "Import new bank/UPI/card statements from the finance folder into transactions (safe to repeat).",
             {}, import_statements),
        Tool("finance_documents", "Find invoices, receipts, tax letters, insurance, contracts and other finance files, with who/when/how much. "
             "Filter by kind, party (who it is from) and dates.",
             {"kind": S("invoice, receipt, payslip, tax, insurance, contract, bank_statement or other"), "party": S("Name, or part of it"),
              "since": S("YYYY-MM-DD"), "until": S("YYYY-MM-DD"), "limit": N("Max rows")}, finance_documents),
        Tool("finance_document_totals", "Add up invoices, receipts, insurance ... by kind, month or who they are from.",
             {"by": S("kind, month or party", enum=["kind", "month", "party"]), "kind": S("Only this kind"), "since": S("YYYY-MM-DD"),
              "until": S("YYYY-MM-DD")}, finance_document_totals),
        Tool("currencies", "The currencies in the ledger and which one the totals are showing.", {}, currencies),
        Tool("agent_list", "All the agents that read, prove and cross-check your data, and whether each one is built or planned.", {}, agent_list),
        Tool("verification_report", "What each verifier agent checked (balances, totals, second reading, payslip vs bank, invoice vs bank, continuity): counts, warnings and failures.", {}, verification_report),
        Tool("files_to_check", "Bank statements that could not be proven correct (not imported) or could not be checked, with the reason.", {}, files_to_check),
        Tool("list_payslips", "Payslips by month: gross, tax, pension, holiday pay and net salary.", {"limit": N("Max months, default 36")}, list_payslips),
        Tool("top_merchants", "Where the money went: spend per merchant, biggest first. Optional month YYYY-MM or since/until dates.",
             {"month": S("YYYY-MM"), "since": S("YYYY-MM-DD"), "until": S("YYYY-MM-DD"), "limit": N("Max rows")}, top_merchants),
        Tool("income_summary", "Money in for a month YYYY-MM: total, by source (employer, interest, refunds, other), the month before, and the payslip figures.",
             {"month": S("YYYY-MM")}, income_summary),
        Tool("monthly_trend", "Spent, income and net for each of the last N months.", {"months": N("How many months, default 6")}, monthly_trend),
        Tool("recurring_payments", "Subscriptions, rent, EMIs and bills: payments that repeat about monthly for a similar amount.", {},
             recurring_payments),
        Tool("uncategorised_spending", "Merchants still in the 'other' category, biggest first.", {}, uncategorised),
        Tool("set_category", "Put all transactions from a merchant into a category (remembered for future imports).",
             {"merchant": S("Merchant name or a description containing it"), "category": S("One of: " + ", ".join(categorize.CATEGORIES))},
             set_category, ("merchant", "category")),
        Tool("delete_transaction", "Delete a transaction by id.", {"id": N("Transaction id")}, delete_transaction, ("id",)),
    ),
)
