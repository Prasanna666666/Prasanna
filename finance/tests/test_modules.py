from datetime import date

import pytest

from finance import dates, db
from finance.modules import ALL, money, notes, people, tasks, tools
from finance.modules.today import briefing_for


def test_migrate_is_idempotent(conn):
    db.migrate(conn, ALL)
    assert conn.execute("SELECT version FROM _migrations WHERE module='tasks'").fetchone()[0] == 1


def test_recurring_task_schedules_next(conn):
    t = tasks.add_task(conn, {"title": "Call Amma", "due": "2026-11-01T18:00", "recurrence": "weekly"})
    out = tasks.complete_task(conn, {"id": t["id"]})
    assert out["next"]["due"] == "2026-11-08T18:00"
    assert [x["due"] for x in tasks.list_tasks(conn, {})] == ["2026-11-08T18:00"]


def test_month_end_clamp():
    assert dates.next_occurrence("2026-01-31", "monthly") == "2026-02-28"


def test_bad_inputs_rejected(conn):
    with pytest.raises(ValueError):
        tasks.add_task(conn, {"title": "x", "due": "tomorrow"})
    with pytest.raises(ValueError):
        money.add_transaction(conn, {"amount": -5})


def test_notes_search_and_tags(conn):
    notes.add_note(conn, {"title": "Dad meds", "body": "BP tablet after breakfast", "tags": "#Health, dad"})
    notes.add_note(conn, {"body": "wifi password"})
    assert len(notes.search_notes(conn, {"query": "tablet breakfast"})) == 1
    assert len(notes.search_notes(conn, {"tag": "health"})) == 1
    assert len(notes.search_notes(conn, {})) == 2


def test_money_summary_with_budget(conn):
    money.set_budget(conn, {"category": "Groceries", "monthly_amount": 5000})
    money.add_transaction(conn, {"amount": 1250.5, "category": "groceries", "date": "2026-11-02"})
    money.add_transaction(conn, {"amount": 30000, "kind": "income", "category": "salary", "date": "2026-11-01"})
    money.add_transaction(conn, {"amount": 999, "date": "2026-10-30"})
    s = money.summary(conn, {"month": "2026-11"})
    assert s["spent"] == 1250.5 and s["net"] == 30000 - 1250.5
    assert s["by_category"][0]["left"] == 5000 - 1250.5


def test_upcoming_dates_and_year_rollover(conn):
    pid = people.add_person(conn, {"name": "Amma", "relation": "mother"})["id"]
    people.add_important_date(conn, {"person_id": pid, "date": "1965-01-05"})
    up = people.upcoming(conn, date(2026, 12, 28), 30)
    assert up[0]["in_days"] == 8 and up[0]["turning"] == 62


def test_briefing(conn):
    tasks.add_task(conn, {"title": "Pay rent", "due": "2026-11-03"})
    tasks.add_task(conn, {"title": "Later", "due": "2026-12-01"})
    assert [t["title"] for t in briefing_for(conn, date(2026, 11, 3))["tasks_due"]] == ["Pay rent"]


def test_tool_names_unique():
    names = [t.name for m in ALL for t in m.tools]
    assert len(names) == len(set(names))
    assert set(tools()) == set(names)


def test_spending_between_two_days_is_exact_and_leaves_transfers_out(conn):
    from finance.modules import money
    from tests.test_tally import tx

    tx(conn, "2026-01-11", 1000, cat="groceries")  # before the trip
    tx(conn, "2026-01-12", 25000, cat="travel", note="Flight")
    tx(conn, "2026-01-30", 4000, cat="food", note="Dinner")
    tx(conn, "2026-01-20", 50000, cat="transfers", note="to savings")
    tx(conn, "2026-01-31", 1000, cat="groceries")  # after
    got = money.spending_between(conn, {"from": "2026-01-12", "to": "2026-01-30"})
    assert got["spent"] == 290.0 and got["payments"] == 2 and [c["category"] for c in got["by_category"]] == ["travel", "food"]
    import pytest

    with pytest.raises(ValueError):
        money.spending_between(conn, {"from": "2026-01-12"})
