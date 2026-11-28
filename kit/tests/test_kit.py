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


def test_an_error_says_where_in_the_code_it_happened_and_nothing_else():
    from kit import log

    def inner():
        raise KeyError("Bank statement.pdf")

    try:
        inner()
    except KeyError as exc:
        place = log.where(exc)
    assert place.startswith("inner, test_kit.py:") and "Bank statement" not in place


def test_a_figure_is_proven_only_by_the_same_signed_value_exactly():
    """ATLAS-ANS-076 / ATLAS-ANS-077: one cent off is unproven; a sign reversal is unproven; no rounding or absolute value is applied."""
    from kit.audit import unproven_figures

    assert unproven_figures("Total EUR 1,250.50", ["balance 1250.49"]) == [1250.5]
    assert unproven_figures("Total 1250.5", ["balance 1250.49"]) == [1250.5]
    assert unproven_figures("Total 1,250", ["balance 1250.49"]) == [1250.0]
    assert unproven_figures("Total 1250.44", ["balance 1250.5"]) == [1250.44]
    assert (
        unproven_figures("Total 1,250.50", ["balance 1250.50"]) == [] and unproven_figures("Total 1250.5", ["balance 1250.50"]) == []
    )  # the same value, written differently
    assert unproven_figures("You gained 250.00", ["net: -250.00"]) == [250.0]  # a positive figure is not proved by a negative one
    assert unproven_figures("You lost -250.00", ["net: 250.00"]) == [-250.0]
    assert unproven_figures("You lost -250.00", ["net: -250.00"]) == [] and unproven_figures("You lost −250.00", ["net: -250.00"]) == []
    assert unproven_figures("change of -12.50 and 12.50", ["a -12.50"]) == [12.5]
    assert (
        unproven_figures("owed 250.00", ["balance (250.00)"]) == [250.0] and unproven_figures("owed -250.00", ["balance (250.00)"]) == []
    )  # accounting brackets mean negative
    assert unproven_figures("0.00 and 100", ["x 0.00 100"]) == []  # zero has no sign
    assert unproven_figures("rent 800", ['{"spent": 800.0}']) == []


def test_a_decimal_comma_figure_is_proven_only_by_the_same_value_never_by_its_integer_part():
    """UC-L22 / exact figures: Dutch and Russian write cents after a comma. Before this fix 480,99 was "proven" by 480,00 (both were read as 480),
    1.234,9 by 1.234,5, and 4,52,000 was read as 52000; every reading is now exact or the figure is unproven."""
    from kit.audit import unproven_figures

    assert unproven_figures("Het totaalbedrag is 480,99 euro.", ["Het totaalbedrag is 480,00 euro."]) == [480.99]
    assert unproven_figures("Het totaalbedrag is 480,00 euro.", ["Het totaalbedrag is 480,00 euro."]) == []
    assert unproven_figures("Сумма 3200,75 евро", ["Сумма к оплате составляет 3200,00 евро."]) == [3200.75]
    assert unproven_figures("1.234,9 kWh", ["1.234,5 kWh"]) == [1234.9] and unproven_figures("1.234,5 kWh", ["1.234,5 kWh"]) == []
    assert unproven_figures("1.234,50", ["1,234.50"]) == [] and unproven_figures("480,00", ["480.00"]) == []  # one value, two conventions
    assert unproven_figures("1\u00a0234,50 €", ["1234.50"]) == [] and unproven_figures("CHF 1'250.50", ["1250.50"]) == []  # no-break space, apostrophe
    assert unproven_figures("1 234,50 €", ["1234.50"]) == [234.5]  # an ordinary space separates words, so this stays unproven rather than guessed


def test_indian_lakh_grouping_is_read_as_one_figure():
    from kit.audit import unproven_figures

    assert unproven_figures("कुल देय राशि ₹4,52,000 है।", ["कुल देय राशि ₹4,52,000 है।"]) == []
    assert unproven_figures("₹4,52,000", ["₹52,000"]) == [452000.0] and unproven_figures("₹1,23,45,678", ["12345678"]) == []
    assert unproven_figures("₹४,५२,०००", ["₹4,52,000"]) == []  # Devanagari digits


def test_an_ambiguous_grouping_is_proven_only_by_the_same_ambiguity():
    """1,250 is 1250 in English and 1.25 in Dutch; it is proven by 1,250 written the same way, never by just one of its readings."""
    from kit.audit import unproven_figures

    assert unproven_figures("Total 1,250", ["Total 1,250"]) == []
    assert unproven_figures("Total 1,250", ["Total 1.25"]) == [1250.0] and unproven_figures("Total 1,250", ["Total 1250"]) == [1250.0]
    assert unproven_figures("version 1.2.3", ["version 1.2.4"]) == [123.0] and unproven_figures("version 1.2.3", ["version 1.2.3"]) == []


def test_a_figure_written_straight_after_japanese_text_is_checked():
    """Japanese writes 支払総額は5800円 with no space; the figure was invisible to the check before (a wrong figure passed as grounded)."""
    from kit.audit import unproven_figures

    assert unproven_figures("支払総額は9999円です。", ["支払総額は5800円です。"]) == [9999.0]
    assert unproven_figures("支払総額は5800円です。", ["支払総額は5800円です。"]) == []
    assert unproven_figures("合計金額は12,800円です。", ["合計金額は１２，８００円です。"]) == []  # full-width digits and comma
    assert unproven_figures("合計金額は12,900円です。", ["合計金額は１２，８００円です。"]) == [12900.0]
    assert unproven_figures("Invoice ACME-2041 totals 1250.50", ["ACME-2041: 1250.50"]) == []  # an identifier's number is still compared


def test_an_amount_whose_integer_part_looks_like_a_year_is_still_checked():
    """UC-L22 (review 6098896232): year-like text was removed before the reply was split into numbers, so 2026.50 lost its integer part and a wrong
    amount near that boundary escaped. Years and dates are now judged on the whole token: 2026.50, 2.026,50 and a 19xx/20xx with a currency beside
    it are amounts; a bare year, an ISO date and a dotted date are not figures."""
    from kit.audit import unproven_figures

    assert unproven_figures("The total is 2026.50 euro.", ["The total is 2026.50 euro."]) == []
    assert unproven_figures("The total is 2026.51 euro.", ["The total is 2026.50 euro."]) == [2026.51]
    assert unproven_figures("Het totaal is 2.026,90 euro.", ["Het totaal is 2.026,50 euro."]) == [2026.9]
    assert unproven_figures("You paid €2026 in rent.", ["rent 2025.00"]) == [2026.0] and unproven_figures("You paid 2026 euro.", ["rent 2026"]) == []
    assert unproven_figures("Paid 1999.00 on 2026-10-05.", ["amount 1999.00 date 2026-10-05"]) == []
    assert unproven_figures("Paid 1999.01 on 2026-10-05.", ["amount 1999.00 date 2026-10-05"]) == [1999.01]
    assert unproven_figures("In 2026 you spent 850.00, due 14.03.2027.", ["spent 850.00"]) == []  # a bare year and a dotted date are dates
