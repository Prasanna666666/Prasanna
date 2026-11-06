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
    monkeypatch.setenv("ATLAS_REQUIRE_ENCRYPTION", "1")
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    monkeypatch.delenv("ATLAS_DB_KEY_FILE", raising=False)
    with pytest.raises(db.EncryptionError):
        db.connect(tmp_path / "x.db")


def test_host_check_and_the_shared_service_call(monkeypatch):
    from kit import http

    allowed = {"127.0.0.1", "localhost", "[::1]"}
    assert http.host_ok("127.0.0.1:8501", allowed) and http.host_ok("[::1]:80", allowed) and http.host_ok("LOCALHOST", allowed)
    assert not http.host_ok("evil.example.com", allowed) and not http.host_ok(None, allowed) and not http.host_ok("localhost.evil.com", allowed)
    with pytest.raises(RuntimeError, match="not valid"):
        http.call_local("ftp://x", "GET", "/", "X-Test", "down")
    with pytest.raises(RuntimeError, match="down"):
        http.call_local("http://127.0.0.1:9", "GET", "/", "X-Test", "down", timeout=1)


def test_signatures_are_checked_only_with_a_secret_and_only_fresh_and_exact():
    from kit import sign

    secret = b"s3cret"
    header = sign.sign("GET", "/api/documents?kind=ticket", secret, now=1000)[sign.HEADER]
    assert sign.valid("GET", "/api/documents?kind=ticket", header, secret, now=1030)
    assert not sign.valid("POST", "/api/documents?kind=ticket", header, secret, now=1030)  # another method
    assert not sign.valid("GET", "/api/documents?kind=medical", header, secret, now=1030)  # another path
    assert not sign.valid("GET", "/api/documents?kind=ticket", header, secret, now=1100)  # too old
    assert not sign.valid("GET", "/api/documents?kind=ticket", header, b"other", now=1030)  # another secret
    assert not sign.valid("GET", "/x", None, secret) and not sign.valid("GET", "/x", "junk", secret)


def test_without_a_secret_nothing_is_signed_or_checked(monkeypatch):
    from kit import sign

    monkeypatch.delenv("PLATFORM_KEY", raising=False)
    assert sign.sign("GET", "/x") == {} and sign.valid("GET", "/x", None) is True


def test_long_text_is_cut_into_overlapping_passages_and_short_text_is_kept_whole():
    assert rag.chunks("") == []
    assert rag.chunks("short text") == ["short text"]
    parts = rag.chunks("word " * 600)
    assert len(parts) > 3 and all(len(p) <= rag.CHUNK for p in parts)
    assert parts[0][-rag.OVERLAP :].strip() in parts[1]  # neighbouring passages share text, so an answer split across a boundary is still found


def test_unproven_figures_ignore_dates_and_small_counts():
    from kit.audit import unproven_figures

    tool = ['{"spent": 850.0, "month": "2026-10", "by_category": [{"category": "rent", "spent": 800.0}]}']
    assert unproven_figures("You spent 850.00 on 2026-10-05, 3 payments, rent 800", tool) == []
    assert unproven_figures("You spent 851.00", tool) == [851.0]
    assert unproven_figures("No tool was used and 9,999 appears", []) == []
