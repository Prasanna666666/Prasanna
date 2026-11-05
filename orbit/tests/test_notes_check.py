"""Your own calculations in your notes are checked for arithmetic and against the app. The note is the example from the brief."""

from orbit import notes_check, verify
from orbit.modules import events, money, notes

NOTE = """Asian games 2026
Tickets: 634.1
Flights: 1179.31
Stay: 280.36
Travel: 130.93
Food and others: 213.66
Total: 2438.36

Shows:
Max Amini✅
Tickets: 63.48✅
Travel: 22.98✅
Food: 10✅
Total: 96.46✅

Cancelled:
Psv vs Bayern✅
Tickets: 110✅
Refund: -175.80✅
Total: -65.80✅
"""


def pay(conn, amount, note="x", kind="expense", day="2026-10-10"):
    return money.add_transaction(conn, {"date": day, "amount": amount, "note": note, "kind": kind})["id"]


def test_the_blocks_of_the_note_are_found_with_signed_amounts():
    blocks = notes_check.blocks_of("Trips", NOTE)
    assert [b.title for b in blocks] == ["Asian games 2026", "Max Amini", "Psv vs Bayern"]
    assert blocks[0].total == 243836 and blocks[0].items[0] == ("Tickets", 63410)
    assert blocks[2].items == [("Tickets", 11000), ("Refund", -17580)] and blocks[2].total == -6580


def test_the_arithmetic_inside_your_own_note_is_checked_to_the_cent(conn):
    notes.add_note(conn, {"title": "Trips", "body": NOTE})
    assert [f.level for f in notes_check.notes_arithmetic(conn)] == ["ok", "ok", "ok"]
    notes.add_note(conn, {"title": "Mistake", "body": NOTE.replace("Total: 2438.36", "Total: 2438.35")})
    bad = [f for f in notes_check.notes_arithmetic(conn) if f.level == "fail"]
    assert len(bad) == 1 and "2438.36" in bad[0].message and "2438.35" in bad[0].message and "difference -0.01" in bad[0].message


def test_the_note_is_compared_line_by_line_with_what_the_app_computed(conn):
    notes.add_note(conn, {"title": "Trips", "body": NOTE})
    for sub, amt in [("tickets", 634.10), ("flights", 1179.31), ("stay", 280.36), ("travel", 130.93), ("food and others", 213.66)]:
        events.assign(conn, {"event": "Asian games 2026", "main": "trips", "sub": sub, "transaction_ids": [pay(conn, amt)]})
    for sub, amt in [("tickets", 63.48), ("travel", 22.98), ("food", 11)]:  # the app has 11 for food: the note says 10
        events.assign(conn, {"event": "Max Amini", "main": "events", "sub": sub, "transaction_ids": [pay(conn, amt)]})
    levels = {f.subject: f for f in notes_check.notes_vs_app(conn)}
    assert levels["Asian games 2026"].level == "ok"
    assert (
        levels["Max Amini"].level == "fail"
        and "'food': note 10.00, app 11.00" in levels["Max Amini"].message
        and "total: note 96.46, app 97.46" in levels["Max Amini"].message
    )
    assert levels["Psv vs Bayern"].level == "warn" and "no event with that name" in levels["Psv vs Bayern"].message


def test_a_line_missing_on_either_side_is_reported(conn):
    notes.add_note(conn, {"title": "Trips", "body": "Derby\nTickets: 50\nBeer: 7\nTotal: 57"})
    events.assign(conn, {"event": "Derby", "main": "sports", "sub": "tickets", "transaction_ids": [pay(conn, 50)]})
    events.assign(conn, {"event": "Derby", "sub": "train", "transaction_ids": [pay(conn, 9)]})
    msg = next(f for f in notes_check.notes_vs_app(conn) if f.subject == "Derby").message
    assert "'beer' 7.00 is in your note but not in the app" in msg and "'train' 9.00 is in the app but not in your note" in msg


def test_the_notes_agents_run_with_every_import_and_show_in_the_report(conn):
    notes.add_note(conn, {"title": "Trips", "body": NOTE.replace("Total: 96.46", "Total: 96.47")})
    verify.run_cross_checks(conn)
    report = money.verification_report(conn)
    assert report["summary"]["notes arithmetic"] == {"ok": 2, "warn": 0, "fail": 1}
