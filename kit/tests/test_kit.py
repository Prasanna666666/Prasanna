"""The shared kit works on its own, with nothing of any app next to it."""

import pytest

from kit import db, extract, rag
from kit.amounts import money_from_printed
from kit.module import Module


def test_printed_amounts_are_read_from_the_figure_itself():
    assert money_from_printed("3.500,00") == 350000 and money_from_printed("1,234.56") == 123456
    assert money_from_printed("€ 61") == 6100 and money_from_printed("60,5") == 6050 and money_from_printed("abc") is None


def test_an_amount_the_model_made_up_is_dropped_because_it_is_not_in_the_document():
    checked = extract.verify_amounts({"kind": "invoice", "total": "60,50", "vat": "99,99"}, "Factuur Ziggo totaal 60,50 btw 10,50")
    assert checked["total"] == 60.5 and checked["vat"] is None and checked["unverified_fields"] == ["vat"]


def test_dates_must_be_written_in_the_document():
    text = "Flight to Delhi on 12 January 2026"
    out = extract.verify_trip_fields({"kind": "ticket", "start_date": "2026-01-12", "end_date": "2026-01-30", "place": "Paris"}, text)
    assert out["start_date"] == "2026-01-12" and out["end_date"] is None and out["place"] == ""


def test_the_database_migrates_a_module_and_retrieval_runs_over_any_sources(tmp_path):
    conn = db.connect(tmp_path / "k.db")
    db.migrate(conn, [Module("notes", ("CREATE TABLE n (id INTEGER PRIMARY KEY, body TEXT);",))])
    conn.execute("INSERT INTO n (body) VALUES ('The rent is 1150 euro per month.')")

    def sources(c):
        return ((f"n{r['id']}", "note", "rent", r["body"]) for r in c.execute("SELECT id, body FROM n"))

    hits = rag.retrieve(conn, "how much is the rent", 3, sources=sources)
    assert hits and "1150" in hits[0]["text"]


def test_a_key_is_required_when_encryption_is_required(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_REQUIRE_ENCRYPTION", "1")
    monkeypatch.delenv("ORBIT_DB_KEY", raising=False)
    monkeypatch.delenv("ORBIT_DB_KEY_FILE", raising=False)
    with pytest.raises(db.EncryptionError):
        db.connect(tmp_path / "x.db")
