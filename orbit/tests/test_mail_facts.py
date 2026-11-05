"""Facts found in mail feed the calculations: what is worth reading, dates that must be written in the document, the per-Update cap, and the mail store."""

import json

from orbit import extract, parser, relevance
from orbit.modules import money
from tests.test_finance import FakeModel, _load


def test_dates_are_found_as_written_in_several_forms():
    text = "Depart 12 January 2026, return 2026-01-30. Check-in 3-2-2026. 15 mrt 2026. March 4, 2026"
    assert extract.dates_in(text) == {"2026-01-12", "2026-01-30", "2026-02-03", "2026-03-15", "2026-03-04"}


def test_a_date_the_model_invents_is_dropped_and_the_place_must_be_written():
    text = "Flight to Delhi on 12 January 2026"
    info = {"kind": "ticket", "start_date": "2026-01-12", "end_date": "2026-01-30", "place": "Delhi"}
    out = extract.verify_trip_fields(info, text)
    assert out["start_date"] == "2026-01-12" and out["end_date"] is None and out["place"] == "Delhi"
    assert extract.verify_trip_fields({"start_date": "2026-01-12", "place": "Paris"}, text)["place"] == ""


def test_an_end_before_the_start_is_dropped():
    text = "from 20 January 2026 until 10 January 2026"
    out = extract.verify_trip_fields({"start_date": "2026-01-20", "end_date": "2026-01-10"}, text)
    assert out["start_date"] == "2026-01-20" and out["end_date"] is None


def test_what_is_worth_reading():
    assert not relevance.worth_reading("promo.eml", "email", "Big sale this week only, enjoy our newsletter with many words in it today")
    assert relevance.worth_reading("m.eml", "email", "Your booking is confirmed. Total paid EUR 480,00 for the hotel in Delhi")
    assert not relevance.worth_reading("scan.pdf", "pdf", "")


def test_mail_is_gated_and_each_judged_once(tmp_path, conn):
    _load(
        conn,
        tmp_path,
        "newsletter-in-the-mailbox",
        text="Hello, a long newsletter with no amounts or documents at all inside it, just chat.",
        area="mail",
        kind="email",
    )
    _load(conn, tmp_path, "hotel-invoice-mail-001", text="FACTUUR hotel total 100,00 EUR betaling", area="mail", kind="email")
    _load(conn, tmp_path, "taxi-invoice-mail-002", text="FACTUUR taxi total 20,00 EUR betaling", area="mail", kind="email")
    assert len(money._pending_documents(conn)) == 2  # one press takes everything worth reading
    assert conn.execute("SELECT COUNT(*) FROM mail_skipped").fetchone()[0] == 1
    model = FakeModel()
    money.import_statements(conn, client=model, model="fake")
    assert model.calls == 2  # the newsletter never reached the model
    assert money._pending_documents(conn) == []


def test_the_mail_store_is_read_once_and_junk_is_skipped(tmp_path):
    store, out = tmp_path / "Mail", tmp_path / "out"
    for box in ("INBOX.mbox", "Junk.mbox"):
        d = store / "V10" / "acct" / box / "Messages"
        d.mkdir(parents=True)
        raw = f"From: a@b.c\nSubject: {box}\nMessage-ID: <{box}@x>\n\nInvoice total EUR 12,00\n".encode()
        (d / "1.emlx").write_bytes(f"{len(raw)}\n".encode() + raw)
    first = parser.process_mail_store(store, out, isolated=False)
    assert first["parsed"] == 1
    assert parser.process_mail_store(store, out, isolated=False)["parsed"] == 0
    names = [json.loads(p.read_text())["name"] for p in out.glob("*.json")]
    assert len(names) == 1 and all(json.loads(p.read_text())["area"] == "mail" for p in out.glob("*.json"))


def test_travel_documents_lists_trips_from_tickets(tmp_path, conn):
    def kind(text):
        return {
            "kind": "ticket",
            "title": "Flight",
            "party": "Air",
            "date": "2026-01-02",
            "total": "480,00",
            "currency": "EUR",
            "start_date": "2026-01-12",
            "place": "Delhi",
        }

    _load(conn, tmp_path, "flight-ticket-mail-003", text="Boarding pass to Delhi on 12 January 2026 total 480,00 EUR", area="mail", kind="email")
    money.import_statements(conn, client=FakeModel(kind=kind), model="fake")
    rows = money.travel_documents(conn, {"place": "delhi", "year": "2026"})
    assert len(rows) == 1 and rows[0]["start_date"] == "2026-01-12" and rows[0]["total"] == 480.0
