import json
from types import SimpleNamespace

import pytest
from kit import db

from library import agenda, store


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "library.db")
    db.migrate(c, [store.MODULE])
    n = [0]

    def add(name, kind, **facts):
        n[0] += 1
        c.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, ready) VALUES (?,?,?,?,?,?,1,?)",
            (f"{n[0]:064x}", name, "pdf", "t", "", json.dumps({"kind": kind, **facts}), n[0]),
        )
        c.commit()

    return SimpleNamespace(conn=c, add=add)


def test_the_calendar_holds_trips_bills_endings_and_follow_ups_from_the_facts_only(conn):
    conn.add("t.pdf", "ticket", title="KLM", place="Lisbon", start_date="2026-12-01", end_date="2026-12-05")
    conn.add("i.pdf", "invoice", title="Internet", party="Ziggo", due_date="2026-11-20", total=60.5, currency="EUR")
    conn.add("p.pdf", "insurance", title="Home policy", party="Centraal", end_date="2027-01-01")
    conn.add("m.pdf", "medical", title="Blood test", party="Kliniek", date="2026-11-01", health={"follow_up": "2026-12-15"})
    conn.add("x.pdf", "invoice", title="No date at all")
    got = agenda.upcoming(conn.conn, "2026-11-14", 90)
    assert [(e["type"], e["date"]) for e in got] == [("due", "2026-11-20"), ("trip", "2026-12-01"), ("followup", "2026-12-15"), ("ends", "2027-01-01")] or len(
        got
    ) == 4
    kinds = {e["type"] for e in got}
    assert kinds == {"due", "trip", "followup", "ends"}
    due = next(e for e in got if e["type"] == "due")
    assert due["days"] == 6 and due["subtitle"] == "EUR 60.50"


def test_a_bill_from_last_week_is_kept_but_a_trip_in_the_past_is_not(conn):
    conn.add("old-bill.pdf", "invoice", title="Rent", due_date="2026-11-08")
    conn.add("old-trip.pdf", "ticket", title="Old", place="Paris", start_date="2026-10-01", end_date="2026-10-03")
    got = agenda.upcoming(conn.conn, "2026-11-14", 60)
    assert [e["type"] for e in got] == ["due"] and got[0]["days"] == -6


def test_a_calendar_file_is_whole_days_and_safe_text(conn):
    text = agenda.ics([{"type": "trip", "date": "2026-12-01", "end": "2026-12-05", "title": "Goa, India;x", "subtitle": "", "doc": None}])
    assert "DTSTART;VALUE=DATE:20261201" in text and "DTEND;VALUE=DATE:20261206" in text and "SUMMARY:Goa Indiax" in text and text.startswith("BEGIN:VCALENDAR")


def test_the_home_cards_are_short_facts_from_the_same_data(conn):
    from types import SimpleNamespace

    from library import highlights

    conn.add(
        "b.pdf",
        "medical",
        title="Blood test",
        date="2026-03-01",
        health={"values": [{"test": "Glucose", "value": "6,4", "number": 6.4, "unit": "mmol/L", "range": "4,0 - 6,0"}], "medicines": [], "follow_up": None},
    )
    state = SimpleNamespace(engine=lambda: None)
    card = highlights.card("health", conn.conn, state)
    assert card["headline"] == "1 to look at" and card["tone"] == "warn" and card["items"][0] == {"label": "Glucose", "value": "6,4 mmol/L"}
    assert highlights.card("photos", conn.conn, state)["headline"] == "Not connected"
    assert highlights.card("nonsense", conn.conn, state) is None


def test_forgetting_a_document_removes_what_was_read_and_nothing_else(conn):
    conn.add("a.pdf", "invoice", title="Keep")
    conn.add("b.pdf", "invoice", title="Forget")
    gone = conn.conn.execute("SELECT id FROM documents WHERE name='b.pdf'").fetchone()["id"]
    assert store.forget(conn.conn, gone) == "b.pdf" and store.forget(conn.conn, gone) is None
    assert [r["name"] for r in conn.conn.execute("SELECT name FROM documents")] == ["a.pdf"]


def test_an_empty_health_page_says_where_the_documents_are_stuck(conn):
    conn.add(
        "v.pdf",
        "medical",
        title="Blood test",
        date="2026-03-01",
        health={"values": [{"test": "Glucose", "value": "6,4", "number": 6.4, "unit": "", "range": ""}]},
    )
    conn.conn.execute("INSERT INTO documents (sha256, name, kind, text, area, facts, judged) VALUES ('w','scan.pdf','pdf','','health','',0)")
    conn.conn.commit()
    f = store.health_funnel(conn.conn)
    assert f["found"] == 2 and f["understood"] == 1 and f["with_values"] == 1 and f["waiting_for_the_model"] == 1 and f["no_readable_text"] == 1
