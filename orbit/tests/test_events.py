"""Events: named groups of payments under the main categories, with sub-lines and totals. The figures are the examples from the brief."""

import json

import pytest

from orbit.modules import events, money


def pay(conn, day, amount, note, kind="expense", category="other"):
    return money.add_transaction(conn, {"date": day, "amount": amount, "note": note, "kind": kind, "category": category})["id"]


def test_the_asian_games_example_adds_up_to_its_total(conn):
    ids = {sub: pay(conn, "2026-09-10", amt, sub) for sub, amt in [("tickets", 634.10), ("flights", 1179.31), ("stay", 280.36), ("travel", 130.93), ("food and others", 213.66)]}
    for sub, i in ids.items():
        events.assign(conn, {"event": "Asian games 2026", "main": "trips", "sub": sub, "transaction_ids": [i]})
    ev = events.list_events(conn)[0]
    assert ev["name"] == "Asian games 2026" and ev["main"] == "trips"
    assert {x["sub"]: x["amount"] for x in ev["lines"]} == {"tickets": 634.10, "flights": 1179.31, "stay": 280.36, "travel": 130.93, "food and others": 213.66}
    assert ev["total"] == 2438.36 and ev["payments"] == 5


def test_a_show_adds_up(conn):
    for sub, amt in [("tickets", 63.48), ("travel", 22.98), ("food", 10)]:
        events.assign(conn, {"event": "Max Amini", "main": "events", "sub": sub, "transaction_ids": [pay(conn, "2026-10-04", amt, sub)]})
    assert events.list_events(conn, {"main": "events"})[0]["total"] == 96.46


def test_a_cancellation_with_a_refund_can_end_below_zero(conn):
    events.assign(conn, {"event": "PSV vs Bayern", "main": "cancellations", "sub": "tickets", "transaction_ids": [pay(conn, "2026-10-01", 110, "tickets")]})
    refund = pay(conn, "2026-10-20", 175.80, "refund psv", kind="income")
    events.assign(conn, {"event": "PSV vs Bayern", "transaction_ids": [refund]})  # income defaults to the 'refund' sub-line
    ev = events.list_events(conn, {"main": "cancellations"})[0]
    assert {x["sub"]: x["amount"] for x in ev["lines"]} == {"tickets": 110.0, "refund": -175.80} and ev["total"] == -65.80
    assert ev["lines"][-1]["sub"] == "refund"  # refunds are listed last


def test_unassigned_spending_is_others_with_its_own_sub_categories_and_events_are_counted_by_main(conn):
    events.assign(conn, {"event": "Max Amini", "main": "events", "sub": "tickets", "transaction_ids": [pay(conn, "2026-10-04", 63.48, "x")]})
    pay(conn, "2026-10-05", 40, "Albert Heijn", category="groceries")
    pay(conn, "2026-10-06", 12, "Kiosk", category="other")
    pay(conn, "2026-10-07", 500, "own account", category="transfers")  # moves between your own accounts are not spending
    by = {m["main"]: m for m in events.spending_by_main(conn, {"month": "2026-10"})}
    assert by["events"]["net"] == 63.48 and by["events"]["events"] == 1 and by["sports"]["net"] == 0
    assert by["others"]["net"] == 52.0 and {s["sub"]: s["amount"] for s in by["others"]["subs"]} == {"groceries": 40.0, "unsorted": 12.0}


def test_events_can_be_renamed_moved_and_deleted_without_losing_the_payments(conn):
    i = pay(conn, "2026-10-04", 20, "x")
    made = events.create_event(conn, {"name": "Derby", "main": "events"})
    events.assign(conn, {"event": made["id"], "sub": "tickets", "transaction_ids": [i]})
    events.update_event(conn, {"id": made["id"], "name": "Ajax derby", "main": "sports"})
    assert events.list_events(conn)[0]["name"] == "Ajax derby" and events.list_events(conn)[0]["main"] == "sports"
    events.delete_event(conn, {"id": made["id"]})
    assert events.list_events(conn) == [] and conn.execute("SELECT COUNT(*) FROM transactions WHERE event_id IS NULL").fetchone()[0] == 1
    with pytest.raises(ValueError):
        events.create_event(conn, {"name": "x", "main": "groceries"})  # only the five main categories exist


def test_the_model_proposes_groups_and_nothing_is_final_until_you_confirm(conn):
    a = pay(conn, "2026-09-10", 634.10, "Asian Games tickets")
    b = pay(conn, "2026-09-11", 1179.31, "KLM flights Hangzhou")
    c = pay(conn, "2026-09-12", 25.0, "Random shop")
    pay(conn, "2026-09-13", 900, "Rent", category="rent")  # routine: never sent to the model

    class Model:
        seen = ""

        def chat(self, model, messages, schema=None, **kw):
            Model.seen = messages[1]["content"]
            return {"content": json.dumps({"assignments": [
                {"id": a, "event": "Asian Games 2026", "main": "trips", "sub": "tickets"}, {"id": b, "event": "Asian Games 2026", "main": "trips", "sub": "flights"},
                {"id": c, "event": "", "main": "others", "sub": ""}, {"id": 9999, "event": "Invented", "main": "trips", "sub": "x"}, {"id": c, "event": "Bad", "main": "nonsense"}]})}

    r = events.suggest(conn, Model(), "fake")
    assert r["considered"] == 3 and r["grouped"] == 2 and "Rent" not in Model.seen
    ev = events.list_events(conn)
    assert [e["name"] for e in ev] == ["Asian Games 2026"] and ev[0]["confirmed"] == 0 and ev[0]["total"] == 1813.41
    events.update_event(conn, {"id": ev[0]["id"], "confirmed": True})
    assert events.list_events(conn)[0]["confirmed"] == 1
