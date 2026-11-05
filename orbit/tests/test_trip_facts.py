"""Dates and places a ticket or booking states must be written in the document; trips are listed from the documents the Documents service handed over."""

from orbit import extract
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


def test_travel_documents_lists_trips_from_tickets(tmp_path, conn):
    text = "Boarding pass to Delhi on 12 January 2026 total 480,00 EUR"
    said = {
        "kind": "ticket",
        "title": "Flight",
        "party": "Air",
        "date": "2026-01-02",
        "total": "480,00",
        "currency": "EUR",
        "start_date": "2026-01-12",
        "place": "Delhi",
    }
    facts = extract.verify_trip_fields(extract.verify_amounts(said, text), text)  # as the Documents service verifies it
    _load(conn, tmp_path, "flight-ticket-mail-003", text=text, area="mail", kind="email", facts=facts)
    money.import_statements(conn, client=FakeModel(), model="fake")
    rows = money.travel_documents(conn, {"place": "delhi", "year": "2026"})
    assert len(rows) == 1 and rows[0]["start_date"] == "2026-01-12" and rows[0]["total"] == 480.0


def test_a_document_the_service_already_described_needs_no_model_here(tmp_path, conn):
    facts = {"kind": "invoice", "title": "Internet", "party": "Ziggo", "date": "2026-10-03", "total": "60.5", "currency": "EUR"}
    _load(conn, tmp_path, "ziggo-invoice-handed-over-01", text="FACTUUR Ziggo 60,50", facts=facts)
    model = FakeModel()
    r = money.import_statements(conn, client=None, model=None)
    assert r["problems"] == [] and model.calls == 0
    assert conn.execute("SELECT party FROM finance_docs").fetchone()["party"] == "Ziggo"
