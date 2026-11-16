"""Reading statements and documents into the ledger: one file at a time, verified, stopping early when a layout cannot be understood."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from kit import extract
from kit.text import day

from .. import (
    audit,
    canary,
    categorize,
    concepts,
    db,
    payslips,
    rates,
    standards,
    statements,
    tables,
    verify,
)
from ..db import rows
from ..findings import Finding, Read


# ---- statements -------------------------------------------------------------------------------------------------------
def _store(conn, d, txns, learned, account: str = "", currency: str = "") -> int:
    new = 0
    scope = re.sub(r"[^A-Za-z0-9]", "", account).upper()
    for ref, t in statements.with_references(txns, scope):
        cur = conn.execute(
            "INSERT OR IGNORE INTO transactions (day, amount_minor, kind, category, note, ref, source, balance_minor, auto, currency, account) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (
                t.day,
                t.amount_minor,
                t.kind,
                categorize.categorise(t.desc, t.kind, learned),
                t.desc[:300],
                ref,
                d["name"][:200],
                t.balance_minor,
                currency,
                scope,
            ),
        )
        new += cur.rowcount
    conn.commit()
    return new


def _day(value) -> str | None:
    found = day(value)
    return found.isoformat() if found else None


def _money(value) -> int | None:
    return round(abs(float(value)) * 100) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _remember_doc(conn, d, info) -> None:
    """Keep what the model read from a finance file: what it is, who it is from, when, how much (every amount was verified against the text)."""
    period = str(info.get("period") or "")
    conn.execute(
        "INSERT OR REPLACE INTO finance_docs (sha256, name, kind, title, summary, party, doc_date, due_date, reference, total_minor, vat_minor, currency, "
        "gross_minor, tax_minor, net_minor, period, start_date, end_date, place, concept) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            d["sha256"],
            d["name"],
            info.get("kind", "other"),
            str(info.get("title") or "")[:120],
            str(info.get("summary") or "")[:300],
            str(info.get("party") or "")[:120],
            _day(info.get("date")),
            _day(info.get("due_date")),
            str(info.get("reference") or "")[:60],
            _money(info.get("total")),
            _money(info.get("vat")),
            str(info.get("currency") or "")[:5].upper(),
            _money(info.get("gross")),
            _money(info.get("tax")),
            _money(info.get("net")),
            period if re.fullmatch(r"20\d{2}(-\d{2})?", period) else "",
            _day(info.get("start_date")),
            _day(info.get("end_date")),
            str(info.get("place") or "")[:80],
            concepts.of(conn, info.get("kind", "other")),
        ),
    )


def travel_documents(conn, a=None):
    """Tickets and bookings found in your files and mail: where to, from when to when (as the document itself writes them), and what they cost."""
    sql, concept_args = concepts.clause("ticket", "booking")
    where, args = [sql], list(concept_args)
    if (a or {}).get("place"):
        where.append("place LIKE ?")
        args.append(f"%{str(a['place'])[:60]}%")
    if (a or {}).get("year"):
        where.append("substr(COALESCE(start_date, doc_date),1,4)=?")
        args.append(str(a["year"])[:4])
    return rows(
        conn.execute(
            "SELECT name, kind, title, party, place, start_date, end_date, doc_date, reference, total_minor/100.0 AS total, currency FROM finance_docs WHERE "
            + " AND ".join(where)
            + " ORDER BY COALESCE(start_date, doc_date), name LIMIT 100",
            args,
        )
    )


def finance_documents(conn, a=None):
    """Finance files by what they are (invoice, receipt, payslip, tax, insurance, contract ...) with who/when/how much."""
    a = a or {}
    where, args = [], []
    if a.get("kind"):  # a concept of Finance ("invoice"), or the model's own word for the file
        asked = " ".join(str(a["kind"]).lower().replace("_", " ").split())
        where.append("(concept=? OR kind=? OR kind=?)")
        args += [asked, asked, str(a["kind"])]
    if a.get("party"):
        where.append("(party LIKE ? OR title LIKE ? OR name LIKE ?)")
        args += [f"%{a['party']}%"] * 3
    if a.get("documents_only"):  # the documents in folders and attached to emails, not the emails themselves
        where.append("sha256 NOT IN (SELECT sha256 FROM documents WHERE kind='email')")
    for key, op in (("since", ">="), ("until", "<=")):
        if a.get(key):
            where.append(f"doc_date {op} ?")
            args.append(a[key])
    sql = (
        "SELECT kind, concept, title, party, doc_date AS date, due_date, reference, total_minor/100.0 AS total, vat_minor/100.0 AS vat, currency, summary, name "
        "FROM finance_docs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY doc_date DESC, name LIMIT ?"
    )
    return rows(conn.execute(sql, [*args, int(a.get("limit", 50))]))


def finance_document_totals(conn, a=None):
    """Totals of invoices / receipts / insurance ... by kind, month or who it is from."""
    a = a or {}
    group = {"month": "substr(doc_date,1,7)", "party": "party", "kind": "kind"}.get(a.get("by", "kind"), "kind")
    sql, concept_args = concepts.clause("bank statement", "payslip", negate=True)
    where, args = ["total_minor IS NOT NULL", sql], list(concept_args)
    if a.get("kind"):
        where.append("kind=?")
        args.append(a["kind"])
    for key, op in (("since", ">="), ("until", "<=")):
        if a.get(key):
            where.append(f"doc_date {op} ?")
            args.append(a[key])
    return rows(
        conn.execute(
            f"SELECT {group} AS grp, COUNT(*) AS documents, SUM(total_minor)/100.0 AS total, SUM(COALESCE(vat_minor,0))/100.0 AS vat "
            f"FROM finance_docs WHERE {' AND '.join(where)} GROUP BY grp ORDER BY total DESC LIMIT 50",
            args,
        )
    )


def _read_standard(kind: str, text: str, name: str) -> Read:
    """MT940 / camt.053: exact formats, no model needed."""
    statements_ = standards.read_mt940(text) if kind == "mt940" else standards.read_camt(text)
    r = Read()
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
    r.findings = [
        Finding(
            "standard reader",
            "fail" if r.issues else "ok",
            name,
            "; ".join(r.issues[:3]) if r.issues else f"{len(r.txns)} transactions; opening balance + transactions = closing balance, to the cent",
        )
    ]
    return r


@dataclass
class _Run:
    """What one import pass did, reported to the user at the end."""

    files: int = 0
    added: int = 0
    duplicates: int = 0
    payslips: int = 0
    empty: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    needs_check: list[dict] = field(default_factory=list)


@dataclass
class _Outcome:
    """What reading one document produced."""

    read: Read | None = None
    slip: payslips.Payslip | None = None
    info: dict = field(default_factory=dict)


def _reader_version() -> str:
    """A fingerprint of how statements are read (the instructions and the shape of the answer the model must give). When it changes, files that were
    left out are tried again once; nothing has to be remembered by hand."""
    import hashlib

    return hashlib.sha256((tables.LAYOUT_PROMPT + json.dumps(tables.LAYOUT_SCHEMA, sort_keys=True)).encode()).hexdigest()[:12]


READER_VERSION = _reader_version()


def _retry_left_out_files(conn) -> None:
    """A file that failed its proof was remembered and never read again. After the reading has improved, give those files one more try."""
    if db.get_setting(conn, "reader_version", "") != READER_VERSION:
        conn.execute("DELETE FROM statement_files WHERE status='needs_check'")
        db.set_setting(conn, "reader_version", READER_VERSION)


def _pending_documents(conn) -> list:
    """The documents the Documents service handed over that are not yet processed: everything from the finance folder, and the others it recognised."""
    done = {r[0] for r in conn.execute("SELECT sha256 FROM statement_files")}
    found = conn.execute("SELECT sha256, name, kind, text, data, area, facts FROM documents WHERE area='finance' OR facts<>'' ORDER BY id").fetchall()
    return [d for d in found if d["sha256"] not in done]


def _document_data(d) -> dict:
    try:
        return json.loads(d["data"]) if d["data"] else {}
    except ValueError:
        return {}


def _import_rates_file(conn, d, data: dict, run: _Run) -> None:
    """The ECB's exchange-rate file is loaded into the rates table; it is not a document about your money."""
    n = rates.store(conn, rates.parse_ecb(data["rows"]))
    _remember_doc(conn, d, {"kind": "other", "title": "ECB exchange rates"})
    conn.execute("INSERT INTO statement_files (sha256, name, found, added, status) VALUES (?,?,0,0,'ok')", (d["sha256"], d["name"]))
    verify.store_file_findings(conn, d["name"], [Finding("rates", "ok", d["name"], f"{n} exchange rates loaded")])
    run.files += 1
    conn.commit()


def _read_document(conn, d, data: dict, client, model, progress, position: tuple[int, int]) -> _Outcome:
    """Read one document: an exact standard needs no model; otherwise the model describes the layout and code reads every figure."""
    own = d["area"] == "finance"  # bank statements are read only from the finance folder; anything else is kept for its facts only
    standard = standards.sniff(d["text"]) if own else None
    if standard:
        info = {"kind": "bank_statement", "title": "Bank statement"}
        _remember_doc(conn, d, info)
        return _Outcome(read=_read_standard(standard, d["text"], d["name"]), info=info)
    out = _Outcome()
    out.info = (
        json.loads(d["facts"]) if d["facts"] else extract.classify(client, model, d["name"], d["text"])
    )  # the Documents service has usually said it already
    _remember_doc(conn, d, out.info)
    if concepts.of(conn, out.info.get("kind")) == "payslip":
        out.slip = payslips.from_model(out.info)
    elif own and tables.looks_like_payment_list(
        data
    ):  # a statement is what holds a list of dated payments: judged by the content, not by what the file was called
        if progress:
            progress(f"Reading file {position[0]} of {position[1]}")
        out.read = verify.read_table_statement(client, model, d["name"], data, d["text"])
    return out


def _record_document(conn, d, out: _Outcome, learned, run: _Run) -> None:
    """Store what was read (only from files that pass their own proof) and remember the file so it is never read twice."""
    rd, status, issues = out.read, "ok", []
    txns: list[statements.Txn] = []
    new = 0
    extra: tuple = ("", None, None, None, None, "")
    if rd is not None:
        status, issues = rd.status, rd.issues
        if status != "needs_check":  # nothing from a file that fails its own proof ever reaches your totals
            txns = rd.txns
            new = _store(conn, d, txns, learned, rd.account, rd.currency)
        else:
            run.needs_check.append({"file": d["name"], "issues": issues[:5]})
        verify.store_file_findings(conn, d["name"], rd.findings)
        extra = (rd.account, rd.first or None, rd.last or None, rd.opening, rd.closing, "; ".join(rd.proofs))
    if out.slip is not None:
        slip = out.slip
        conn.execute(
            "INSERT OR IGNORE INTO payslips VALUES (?,?,?,?,?,?,?,?)",
            (d["sha256"], d["name"], slip.period, slip.gross_minor, slip.net_minor, slip.tax_minor, slip.pension_minor, slip.holiday_minor),
        )
        run.payslips += 1
    conn.execute(
        "INSERT INTO statement_files (sha256, name, found, added, status, issues, account, period_start, period_end, opening_minor, closing_minor, proofs, currency) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (d["sha256"], d["name"], len(txns), new, status, "; ".join(issues)[:500], *extra, rd.currency if rd is not None else ""),
    )
    audit.record(conn, "file read", f"{d['name']}: {status}, {len(txns)} payments, {new} new")
    run.files += 1
    run.added += new
    run.duplicates += len(txns) - new
    if not txns and out.slip is None and rd is not None and status != "needs_check":
        run.empty.append(d["name"])
    conn.commit()


def _after_import(conn, client, model, progress, run: _Run) -> None:
    """Convert to euros, run every cross-check, then let the model sort new merchants and group trips (it sees only names)."""
    rates.convert_all(conn)  # every payment in euros at the rate of its own day
    verify.run_cross_checks(conn)  # payslips vs bank, invoices vs bank, continuity, plausibility: every time, on everything
    if client is None or not model or not run.added:
        return
    try:
        categorize.recategorise_with_model(conn, client, model)
    except RuntimeError as exc:
        run.problems.append(f"Imported, but the merchants could not be sorted by the model: {exc}")
    try:
        from . import events

        events.suggest(conn, client, model, progress=progress)
    except RuntimeError as exc:
        run.problems.append(f"Imported, but the payments could not be grouped into trips and events: {exc}")


def _needs_model(d) -> bool:
    """Only a statement's layout (or a document nobody has described yet) needs the model here; the exact bank standards and described documents do not."""
    if d["area"] == "finance" and standards.sniff(d["text"]):
        return False
    return d["area"] == "finance" and tables.looks_like_payment_list(_document_data(d))  # only a list of dated payments needs its layout worked out


def import_statements(conn, a=None, client=None, model=None, progress=None):
    """Read every finance document the parser has produced and not yet imported. Safe to repeat: a line is never added twice.

    Bank standards (MT940, camt.053) are read exactly, without a model. Other statements: the local model only describes the layout, code reads every
    figure, and verifier agents (balances, totals, a second independent reading) must all agree. A file that fails is not counted. Without the model,
    only the exact standards can be imported (a guess at a layout could silently give wrong numbers)."""
    concepts.resolve(conn, client, model)  # what each kind of file means to Finance (the model decides once per kind)
    _retry_left_out_files(conn)
    learned = categorize.learned_rules(conn)
    run = _Run()
    docs = _pending_documents(conn)
    no_model = "The local model is not running, so these statements cannot be read. Start Ollama and try again."
    if client is not None and model and any(_needs_model(d) for d in docs):
        try:
            broken = canary.model_check(client, model)
        except RuntimeError as exc:
            broken = f"the model could not be reached ({exc})"
        if broken:  # before touching a single file: this is the model's problem, so none of the files is marked as failed
            run.problems.append(f"Nothing was read: {broken}. This is a problem with the model, not with your files, and they will be tried again.")
            return _finished(conn, client, model, progress, run, learned_done=False)
    streak: list[str] = []
    for index, d in enumerate(docs, 1):
        data = _document_data(d)
        if rates.looks_like_ecb(data.get("rows")):
            _import_rates_file(conn, d, data, run)
            continue
        if _needs_model(d) and (client is None or not model):
            if no_model not in run.problems:
                run.problems.append(no_model)
            continue
        try:
            out = _read_document(conn, d, data, client, model, _with_failures(progress, run), (index, len(docs)))
        except extract.Unclear:  # the model could not make sense of this one: it is not marked as read, and is tried again next time
            run.problems.append(f"{d['name']}: the model could not make sense of it this time; it will be tried again")
            continue
        except RuntimeError as exc:  # the model could not be reached: stop, nothing is marked as done
            run.problems.append(str(exc))
            break
        _record_document(conn, d, out, learned, run)
        streak = [*streak, d["sha256"]] if _layout_failed(out) else []
        if len(streak) >= FAIL_FAST:
            _stop_early(conn, run, streak)
            break
    return _finished(conn, client, model, progress, run)


FAIL_FAST = 3  # this many files in a row whose layout could not be understood: stop, do not go through all of them to find out
LAYOUT_FAILED = "it could not be read as a list of payments"


def _layout_failed(out: _Outcome) -> bool:
    return out.read is not None and out.read.status == "needs_check" and bool(out.read.issues) and out.read.issues[0].startswith(LAYOUT_FAILED)


def _with_failures(progress, run: _Run):
    """The progress line also says how many files could not be read so far, so a problem shows after the first files, not after the last."""
    if progress is None:
        return None
    return lambda message: progress(message + (f" ({len(run.needs_check)} could not be read so far)" if run.needs_check else ""))


def _stop_early(conn, run: _Run, streak: list[str]) -> None:
    """Several files in a row failed the same way: that is the model struggling, not several bad files. Stop now, forget those failures so they are
    tried again, and say so plainly."""
    conn.executemany("DELETE FROM statement_files WHERE sha256=?", [(sha,) for sha in streak])
    conn.commit()
    del run.needs_check[-len(streak) :]
    run.files -= len(streak)
    run.problems.append(
        f"Stopped after {len(streak)} files in a row could not be read. That usually means the model is struggling, not your files. "
        "Nothing was lost: these and the rest will be tried again at the next Update."
    )


def _finished(conn, client, model, progress, run: _Run, learned_done: bool = True) -> dict:
    if learned_done:
        _after_import(conn, client, model, progress, run)
    return {
        "files": run.files,
        "new_transactions": run.added,
        "already_had": run.duplicates,
        "payslips": run.payslips,
        "files_with_no_transactions": run.empty,
        "needs_check": run.needs_check,
        "problems": run.problems,
    }
