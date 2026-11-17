"""A text cut to fit its field is never cut silently: the cut is recorded with where it came from, which field, how long it was and how much was kept."""

import json

from finance import db as finance_db
from finance import web
from finance.modules import statement_import

DOC = {"sha256": "a" * 64, "name": "bank-march.pdf"}


def _audit(conn):
    return [dict(r) for r in conn.execute("SELECT source, field, original_chars, kept_chars FROM truncation_audit ORDER BY id")]


def test_a_long_title_summary_party_reference_and_place_are_cut_and_recorded(conn):
    info = {"kind": "invoice", "title": "T" * 500, "summary": "S" * 900, "party": "P" * 130, "reference": "R" * 61, "place": "L" * 81}
    statement_import._remember_doc(conn, DOC, info)
    row = conn.execute("SELECT title, summary, party, reference, place FROM finance_docs").fetchone()
    assert [len(v) for v in row] == [120, 300, 120, 60, 80]
    cuts = {c["field"]: c for c in _audit(conn)}
    assert set(cuts) == {"title", "summary", "party", "reference", "place"}
    assert (cuts["title"]["original_chars"], cuts["title"]["kept_chars"], cuts["title"]["source"]) == (500, 120, "bank-march.pdf")


def test_text_that_fits_is_not_recorded(conn):
    statement_import._remember_doc(conn, DOC, {"kind": "invoice", "title": "Electricity", "summary": "March"})
    assert _audit(conn) == []


def test_a_long_payment_description_is_cut_and_recorded(conn):
    class Line:
        day, amount_minor, kind, balance_minor, desc = "2026-03-02", 1250, "expense", None, "Betaling " + "x" * 400

    statement_import._store(conn, DOC, [Line()], {}, "NL00BANK0123456789", "EUR")
    assert len(conn.execute("SELECT note FROM transactions").fetchone()[0]) == 300
    assert [(c["field"], c["original_chars"], c["kept_chars"]) for c in _audit(conn)] == [("description", 409, 300)]


def test_the_cuts_can_be_read_back_through_the_api(conn):
    statement_import._remember_doc(conn, DOC, {"kind": "invoice", "title": "T" * 200})
    out = web.GET_ROUTES["/api/truncations"](None, conn, {})
    assert out["cuts"][0]["field"] == "title" and out["cuts"][0]["original_chars"] == 200
    json.dumps(out)
    assert finance_db.rows


def test_the_line_that_carries_a_date_is_kept_and_returned_with_the_document(conn):
    info = {
        "kind": "invoice",
        "title": "Electricity",
        "date": "2026-03-02",
        "date_source": "Factuurdatum: 2 maart 2026",
        "due_date": "2026-03-16",
        "due_date_source": "Betaal uiterlijk 16 maart 2026",
    }
    statement_import._remember_doc(conn, DOC, info)
    row = statement_import.finance_documents(conn, {})[0]
    assert (row["date"], row["date_source"]) == ("2026-03-02", "Factuurdatum: 2 maart 2026")
    assert (row["due_date"], row["due_date_source"]) == ("2026-03-16", "Betaal uiterlijk 16 maart 2026")


def test_a_source_line_is_not_kept_for_a_date_that_was_not_verified(conn):
    statement_import._remember_doc(conn, DOC, {"kind": "invoice", "title": "T", "date": None, "date_source": "Datum: 30 februari 2026"})
    assert statement_import.finance_documents(conn, {})[0]["date_source"] == ""


def test_the_documents_page_shows_the_source_line_under_each_date():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "src" / "finance" / "static" / "app.js").read_text()
    assert "d.date_source" in js and "d.due_date_source" in js and "datesource" in js
