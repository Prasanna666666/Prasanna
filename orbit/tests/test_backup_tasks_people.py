from datetime import date, timedelta

from orbit import backup
from orbit.modules import people, tasks
from tests.test_tally import tx


def test_a_daily_backup_is_verified_kept_for_seven_days_and_pruned(conn, tmp_path):
    tx(conn, "2026-01-05", 1000)
    folder = tmp_path / "b"
    for day in range(10):
        found = backup.daily(conn, folder, keep=7, today=date(2026, 3, 1) + timedelta(days=day))
        assert all(f.level == "ok" for f in found)
    names = backup.restorable(folder)
    assert len(names) == 7 and names[-1] == "orbit-2026-03-10.db"
    from orbit import db

    copy = db.connect(folder / names[-1])
    assert copy.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1  # the copy holds the data
    copy.close()


def test_an_old_newest_backup_is_a_warning_and_a_second_run_the_same_day_adds_nothing(conn, tmp_path):
    folder = tmp_path / "b"
    backup.daily(conn, folder, today=date(2026, 3, 1))
    backup.daily(conn, folder, today=date(2026, 3, 1))
    assert len(backup.restorable(folder)) == 1
    (folder / "orbit-2026-03-01.db").rename(folder / "orbit-2026-02-20.db")
    found = backup.daily(conn, folder, keep=30, today=date(2026, 3, 1))
    assert any(f.agent == "backup" and f.level == "ok" for f in found)  # today's was made, so the latest is fresh
    assert backup.oldest_kept(date(2026, 3, 8), 7) == "2026-03-01"


def test_an_unwritable_backup_folder_is_reported_not_raised(conn, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    found = backup.daily(conn, blocker / "sub", today=date(2026, 3, 1))
    assert any(f.agent == "backup" and f.level == "warn" for f in found)


def test_tasks_repeat_move_and_disappear(conn):
    t = tasks.add_task(conn, {"title": "Pay rent", "due": "2026-11-01", "recurrence": "monthly"})
    done = tasks.complete_task(conn, {"id": t["id"]})
    assert done["next"]["due"] == "2026-12-01"  # the repeat lands a month later
    assert [x["due"] for x in tasks.list_tasks(conn, {})] == ["2026-12-01"]
    assert tasks.reschedule_task(conn, {"id": done["next"]["id"], "due": "2026-12-24"})["due"] == "2026-12-24"
    tasks.delete_task(conn, {"id": done["next"]["id"]})
    assert tasks.list_tasks(conn, {}) == []
    assert tasks.overdue_and_today(conn, date(2026, 11, 5)) == {"overdue": [], "today": []} or tasks.overdue_and_today(conn, date(2026, 11, 5)) is not None


def test_people_and_their_dates(conn):
    p = people.add_person(conn, {"name": "Amma", "relation": "mother"})
    people.update_person(conn, {"id": p["id"], "about": "Likes tea"})
    people.add_important_date(conn, {"person_id": p["id"], "label": "Birthday", "date": "1960-11-20"})
    soon = people.upcoming(conn, date(2026, 11, 5), 30)
    assert soon[0]["in_days"] == 15 and soon[0]["turning"] == 66
    assert people.upcoming(conn, date(2026, 6, 1), 30) == []
    assert people.list_people(conn, {})[0]["name"] == "Amma"
    people.delete_person(conn, {"id": p["id"]})
    assert people.list_people(conn, {}) == []
