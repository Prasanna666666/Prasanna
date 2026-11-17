"""What the assistant adds at once can be taken back as a group: the latest question's additions, only after the person's own yes, and only what still exists (O-7)."""

from datetime import UTC, datetime

from finance import changes, web
from finance.modules import events

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def _tool(conn, name, args, turn, said="please add that"):
    return web._post_tool(None, conn, {"name": name, "args": args, "user_text": said, "turn": turn})


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_the_latest_questions_additions_are_taken_back_after_a_yes_and_nothing_else(conn):
    _tool(conn, "add_note", {"body": "older note"}, "q1")  # an earlier question
    _tool(conn, "add_person", {"name": "Alex Example"}, "q2")
    person = conn.execute("SELECT id FROM people").fetchone()["id"]
    _tool(conn, "add_important_date", {"person_id": person, "date": "1990-05-04"}, "q2")
    _tool(conn, "add_task", {"title": "Renew insurance"}, "q2")
    assert (_count(conn, "people"), _count(conn, "important_dates"), _count(conn, "tasks"), _count(conn, "notes")) == (1, 1, 1, 1)
    out = _tool(conn, "undo_last_additions", {}, "q3", said="take that back")
    assert out["ok"] and out["data"]["changed_anything"] is False  # only prepared
    assert "Alex Example" in out["data"]["waiting_for_the_person"] and "Renew insurance" in out["data"]["waiting_for_the_person"]
    assert _count(conn, "people") == 1
    changes.confirm(conn, "yes", "q4", NOW)
    assert (_count(conn, "people"), _count(conn, "important_dates"), _count(conn, "tasks")) == (0, 0, 0)
    assert _count(conn, "notes") == 1, "the earlier question's note stays"


def test_a_message_that_is_not_a_yes_takes_back_nothing(conn):
    _tool(conn, "add_task", {"title": "Keep me"}, "q1")
    _tool(conn, "undo_last_additions", {}, "q2", said="undo that")
    changes.confirm(conn, "hmm, not sure", "q3", NOW)
    assert _count(conn, "tasks") == 1


def test_a_second_undo_goes_back_one_more_question_and_an_empty_journal_says_so(conn):
    _tool(conn, "add_note", {"body": "first"}, "q1")
    _tool(conn, "add_note", {"body": "second"}, "q2")
    _tool(conn, "undo_last_additions", {}, "q3")
    changes.confirm(conn, "yes", "q4", NOW)
    assert [r["body"] for r in conn.execute("SELECT body FROM notes")] == ["first"]
    _tool(conn, "undo_last_additions", {}, "q5")
    changes.confirm(conn, "yes", "q6", NOW)
    assert _count(conn, "notes") == 0
    assert web.additions.undo_last_additions(conn)["removed"] == 0


def test_an_event_the_person_already_had_is_not_journaled_so_undo_never_removes_it(conn):
    events.create_event(conn, {"name": "Lisbon trip", "main": "trips"})  # made by the person, not by the assistant
    _tool(conn, "create_event", {"name": "Lisbon trip", "main": "trips"}, "q1")  # the assistant only finds it
    assert conn.execute("SELECT COUNT(*) FROM assistant_additions").fetchone()[0] == 0
    out = _tool(conn, "undo_last_additions", {}, "q2")
    changes.confirm(conn, "yes", "q3", NOW)
    assert _count(conn, "events") == 1
    assert "nothing" in out["data"]["waiting_for_the_person"]
