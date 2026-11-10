"""Health (locked; values and medicines exactly as printed) and Travel (trips from tickets, bookings and photos)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from kit import db

from library import store, tools, travel, web


@pytest.fixture
def lib(tmp_path):
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    n = [0]

    def add(name, kind, text="t", **facts):
        n[0] += 1
        conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, ready) VALUES (?,?,?,?,?,?,1,?)",
            (f"{n[0]:064x}", name, "pdf", text, "", json.dumps({"kind": kind, **facts}), n[0]),
        )
        conn.commit()

    store.set_health_unlocked(False)
    yield SimpleNamespace(conn=conn, add=add, state=SimpleNamespace(engine=lambda: None, picture_text=lambda: None))
    store.set_health_unlocked(False)


def _blood(lib):
    health = {
        "values": [{"test": "Hemoglobine", "value": "8,4", "number": 8.4, "unit": "mmol/L", "range": "7,5 - 10,0"}],
        "medicines": [{"name": "Metformine", "dose": "500 mg", "duration": ""}],
        "follow_up": "2099-06-01",
    }
    lib.add("bloed-maart.pdf", "medical", title="Blood test", date="2026-03-01", party="Kliniek", health=health)
    health2 = {"values": [{"test": "hemoglobine", "value": "9,0", "number": 9.0, "unit": "mmol/L", "range": "7,5 - 10,0"}], "medicines": [], "follow_up": None}
    lib.add("bloed-juni.pdf", "medical", title="Blood test", date="2026-06-02", party="Kliniek", health=health2)


def test_health_is_locked_nothing_comes_out_and_the_assistant_is_told_why(lib):
    _blood(lib)
    for fn in (store.health_timeline, store.health_values, store.health_medicines):
        assert fn(lib.conn) == {"locked": True, "held_back": 2}
    out = tools.run(lib.state, lib.conn, "health_values", {})
    assert out["ok"] and out["data"]["locked"] is True and "unlock" in out["data"]["note"].lower()


def test_unlocked_health_shows_each_measurement_over_time_exactly_as_printed(lib):
    _blood(lib)
    store.set_health_unlocked(True)
    tests = store.health_values(lib.conn)["tests"]
    assert len(tests) == 1 and tests[0]["test"] == "Hemoglobine" and tests[0]["unit"] == "mmol/L"
    assert [(r["date"], r["value"], r["range"]) for r in tests[0]["readings"]] == [("2026-03-01", "8,4", "7,5 - 10,0"), ("2026-06-02", "9,0", "7,5 - 10,0")]
    assert store.health_values(lib.conn, "cholesterol")["tests"] == []
    assert [m["name"] for m in store.health_medicines(lib.conn)["medicines"]] == ["Metformine"]
    assert [d["name"] for d in store.health_timeline(lib.conn)["documents"]] == ["bloed-juni.pdf", "bloed-maart.pdf"]  # newest first
    assert [f["date"] for f in store.health_followups(lib.conn, "2026-07-01")["follow_ups"]] == ["2099-06-01"]
    assert store.health_followups(lib.conn, "2100-01-01")["follow_ups"] == []


def test_medical_details_are_filled_for_documents_judged_before_and_use_the_model_once(lib):
    lib.add("oud.pdf", "medical", text="Hemoglobine 8,4 mmol/L", title="Old", date="2025-01-01")
    calls = []

    class Model:
        def chat(self, model, messages, schema=None, **kw):
            calls.append(1)
            return {"content": json.dumps({"values": [{"test": "Hemoglobine", "value": "8,4", "unit": "mmol/L"}]})}

    assert store.fill_health_details(lib.conn, Model(), "m") == 1 and store.fill_health_details(lib.conn, Model(), "m") == 0 and len(calls) == 1
    store.set_health_unlocked(True)
    assert store.health_values(lib.conn)["tests"][0]["readings"][0]["value"] == "8,4"


def test_trips_come_from_tickets_and_bookings_with_exact_booked_totals(lib):
    lib.add(
        "flight.pdf", "ticket", title="KLM", start_date="2099-01-10", end_date="2099-01-10", place="Bengaluru", reference="ABC123", total=612.5, currency="EUR"
    )
    lib.add("hotel.pdf", "booking", title="Taj", start_date="2099-01-10", end_date="2099-01-20", place="Bengaluru", total=300.25, currency="EUR")
    lib.add("old.pdf", "ticket", title="Old", start_date="2020-05-01", end_date="2020-05-05", place="Lisbon")
    lib.add("receipt.pdf", "receipt", title="Dinner", date="2099-01-12", total=45.0, currency="EUR")
    found = travel.trips(lib.conn, None, "2026-11-10")
    assert [(t["place"], t["status"]) for t in found] == [("Bengaluru", "upcoming"), ("Lisbon", "past")]  # not yet over first, then the past, newest first
    d = travel.detail(lib.conn, None, "Bengaluru", "2099-01-10", "2099-01-20")
    assert [t["name"] for t in d["tickets"]] == ["flight.pdf", "hotel.pdf"] and d["booked_totals"] == {"EUR": 912.75}
    assert [o["name"] for o in d["other_documents"]] == ["receipt.pdf"] and d["tickets"][0]["reference"] == "ABC123"
    out = tools.run(lib.state, lib.conn, "trip_details", {"place": "bengaluru"})
    assert out["ok"] and out["data"]["trips"][0]["booked_totals"] == {"EUR": 912.75}
    assert [t["place"] for t in tools.run(lib.state, lib.conn, "upcoming_trips", {})["data"]["trips"]] == ["Bengaluru"]


def test_the_calendar_file_lists_every_trip_as_whole_days():
    ics = travel.calendar([{"place": "Goa, India", "start": "2026-12-30", "end": "2027-01-02"}])
    assert (
        "DTSTART;VALUE=DATE:20261230" in ics and "DTEND;VALUE=DATE:20270103" in ics and "SUMMARY:Trip: Goa India" in ics and ics.startswith("BEGIN:VCALENDAR")
    )


def test_the_travel_and_health_routes_exist_and_a_trip_needs_real_days(lib):
    for route in ("/api/travel/trips", "/api/travel/trip", "/api/medical/timeline", "/api/medical/values", "/api/medical/medicines", "/api/medical/followups"):
        assert route in web.GET_ROUTES
    with pytest.raises(web.Fail):
        web._get_travel_trip(lib.state, lib.conn, {"place": "x", "start": "not", "end": "2026-01-01"})


def _packing(lib, action, **extra):
    return travel.packing_action(lib.conn, {"place": "Goa", "start": "2099-01-10", "end": "2099-01-14", "action": action, **extra})


def test_a_packing_list_starts_from_a_standard_list_whose_quantities_follow_from_the_days(lib):
    r = _packing(lib, "seed")  # five days
    texts = [i["text"] for i in r["items"]]
    assert "Tops: 5" in texts and "Underwear and socks: 6" in texts and "Trousers or skirts: 3" in texts and "Passport or ID" in texts
    assert r["packed"] == 0 and r["total"] == len(r["items"]) and r["items"][0]["section"] == "Documents"
    assert [
        i["text"]
        for i in travel.packing_action(lib.conn, {"place": "X", "start": "2099-01-01", "end": "2099-03-01", "action": "seed"})["items"]
        if i["text"].startswith(("Tops", "Underwear", "Trousers"))
    ] == [
        "Tops: 7",
        "Underwear and socks: 8",
        "Trousers or skirts: 4",
    ]  # a long trip: you wash, so the numbers stop growing
    with pytest.raises(ValueError, match="already has a list"):
        _packing(lib, "seed")


def test_items_can_be_added_ticked_and_removed_and_each_trip_has_its_own_list(lib):
    _packing(lib, "seed")
    added = _packing(lib, "add", text="  Camera   and lens ", section="Electronics")
    item = next(i for i in added["items"] if i["text"] == "Camera and lens")
    assert item["section"] == "Electronics" and item["done"] == 0
    assert _packing(lib, "toggle", id=item["id"])["packed"] == 1 and _packing(lib, "toggle", id=item["id"])["packed"] == 0
    assert all(i["id"] != item["id"] for i in _packing(lib, "delete", id=item["id"])["items"])
    assert travel.packing(lib.conn, "Lisbon", "2099-01-10")["total"] == 0  # another trip: nothing
    other = travel.packing_action(lib.conn, {"place": "Lisbon", "start": "2099-01-10", "end": "2099-01-12", "action": "add", "text": "Guidebook"})
    assert _packing(lib, "toggle", id=other["items"][0]["id"])["packed"] == 0  # an item of another trip cannot be changed from this one
    for bad in ({"action": "add", "text": "  "}, {"action": "nonsense"}):
        with pytest.raises(ValueError):
            _packing(lib, bad["action"], **{k: v for k, v in bad.items() if k != "action"})


def test_the_assistant_can_say_what_is_left_to_pack(lib):
    lib.add("flight.pdf", "ticket", title="KLM", start_date="2099-01-10", end_date="2099-01-14", place="Goa")
    _packing(lib, "seed")
    first = travel.packing(lib.conn, "Goa", "2099-01-10")["items"][0]
    _packing(lib, "toggle", id=first["id"])
    out = tools.run(lib.state, lib.conn, "packing_list", {"place": "goa"})["data"]["lists"][0]
    assert out["packed"] == 1 and first["text"] not in out["still_to_pack"] and len(out["still_to_pack"]) == out["total"] - 1


def test_the_packing_routes_exist_and_refuse_a_trip_without_days(lib):
    assert "/api/travel/packing" in web.GET_ROUTES and "/api/travel/packing" in web.POST_ROUTES
    with pytest.raises(web.Fail):
        web._post_packing(lib.state, lib.conn, {"place": "Goa", "start": "x", "end": "y", "action": "seed"})
