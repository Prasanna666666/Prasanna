"""Stage 4, UC-044: usage by category and what disk pressure may and may not do."""

from __future__ import annotations

import pytest

from atlas_core.storage import ACTIONS, GIB, NEVER, pressure_of, report

pytestmark = pytest.mark.criterion(15)


def fake_disk(total, free):
    return lambda path: (total, total - free, free)


def test_usage_is_reported_by_category_and_originals_are_not_counted(tmp_path):
    data = tmp_path / "core"
    (data / "models" / "m").mkdir(parents=True)
    (data / "history").mkdir()
    (data / "tasks.db").write_bytes(b"t" * 100)
    (data / "documents.db").write_bytes(b"d" * 300)
    (data / "mail.db").write_bytes(b"m" * 200)
    (data / "designation.db").write_bytes(b"s" * 50)
    (data / "models" / "m" / "w").write_bytes(b"w" * 1000)
    (data / "history" / "h.db").write_bytes(b"h" * 20)
    (data / "stray.bin").write_bytes(b"x" * 7)
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "b").write_bytes(b"b" * 11)
    r = report(data, backups_dir=backups, budget_bytes=1000, usage=fake_disk(100 * GIB, 60 * GIB))
    assert r.bytes_by_category == {"tasks": 100, "designation": 50, "indexes": 500, "models": 1000, "history": 20, "other": 7, "backups": 11}
    assert r.over_budget is True and r.pressure == "ok" and r.actions == ()


@pytest.mark.parametrize(
    ("free_gib", "total_gib", "level"),
    [
        (60, 100, "ok"),
        (9, 100, "low"),
        (5, 100, "low"),
        (2.5, 100, "critical"),
        (1.5, 100, "critical"),
        (200, 1000, "ok"),
        (50, 1000, "low"),
        (25, 1000, "critical"),
    ],
)
def test_pressure_levels_follow_the_stricter_of_the_fraction_and_the_floor(free_gib, total_gib, level):
    assert pressure_of(int(free_gib * GIB), total_gib * GIB) == level


def test_pressure_can_pause_derived_work_and_warn_but_never_delete_anything():
    for level, actions in ACTIONS.items():
        assert not set(actions) & set(NEVER), level
        assert all(a.startswith(("tell_", "pause_", "defer_", "refuse_")) for a in actions), level
    assert "tell_owner" in ACTIONS["low"] and "pause_index_growth" in ACTIONS["critical"] and ACTIONS["ok"] == ()


def test_a_report_of_an_empty_or_missing_folder_is_zero_not_an_error(tmp_path):
    r = report(tmp_path / "nothing", usage=fake_disk(100 * GIB, 50 * GIB))
    assert sum(r.bytes_by_category.values()) == 0 and r.over_budget is False


def test_a_nearly_full_disk_stops_every_index_from_growing_and_says_so_and_recovery_resumes_it(tmp_path):
    import time

    from test_app import World

    world = World(tmp_path, mail=True)
    state = {"free": 500 * GIB}
    try:
        core = world.build()
        core.config.disk_usage = lambda path: (1000 * GIB, 1000 * GIB - state["free"], state["free"])
        state["free"] = 1 * GIB  # critical: below 3% and below 2 GiB
        core.start()
        world.enable(core, "documents", "mail")
        time.sleep(0.6)
        for name in ("documents", "mail"):
            cov = core.indexes[name].coverage()
            assert cov["paused"] == "disk_pressure" and cov["total"] == 0 and cov["complete"] is False  # nothing was taken in, and the pause is visible
        assert world.mailbox.reads == 0
        state["free"] = 800 * GIB  # space is back
        world.wait_indexed(core)
        assert core.indexes["documents"].coverage()["paused"] is None and core.indexes["documents"].coverage()["total"] > 0
    finally:
        world.close()
