"""A real database made by an older build (commit 5f7fa48, before the assistant's prepared changes, the truncation audit and the date-source columns) is upgraded by the current code: every row survives exactly, the new tables and columns exist, the database is sound, and a second start changes nothing (review item O-12, Finance). The file holds invented rows only. It was written by the code of that commit, not by this one."""

import sqlite3
from pathlib import Path

from finance import db
from finance.modules import ALL

FIXTURE = Path(__file__).parent / "fixtures" / "release-5f7fa48.sql"  # a text dump: the repository keeps no database files (test_data_boundary)


def _build_old(path):
    old = sqlite3.connect(path)
    old.executescript(FIXTURE.read_text(encoding="utf-8"))
    old.commit()
    old.close()


def _upgrade(tmp_path):
    path = tmp_path / "finance.db"
    _build_old(path)
    conn = db.connect(path)
    db.migrate(conn, ALL)
    return path, conn


def test_the_fixture_is_really_the_old_schema(tmp_path):
    _build_old(tmp_path / "old.db")
    old = sqlite3.connect(tmp_path / "old.db")
    tables = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "transactions" in tables and "assistant_changes" not in tables and "truncation_audit" not in tables
    assert old.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 4


def test_every_row_survives_the_upgrade_exactly(tmp_path):
    _, conn = _upgrade(tmp_path)
    got = [tuple(r) for r in conn.execute("SELECT day, amount_minor, kind, category, note, balance_minor, account FROM transactions ORDER BY day, ref")]
    assert got == [
        ("2026-09-01", 200000, "income", "salary", "Acme BV Salaris", None, "NL00TEST0000000001"),
        ("2026-09-03", 2345, "expense", "groceries", "Albert Heijn Utrecht", 197655, "NL00TEST0000000001"),
        ("2026-09-05", 110000, "expense", "housing", "Huur september", 87655, "NL00TEST0000000001"),
        ("2026-09-09", 1999, "expense", "subscriptions", "Streaming", 85656, "NL00TEST0000000001"),
    ]
    assert conn.execute("SELECT closing_minor, status FROM statement_files").fetchone()[:] == (85656, "verified")
    assert tuple(conn.execute("SELECT gross_minor, net_minor FROM payslips").fetchone()) == (350000, 251260)
    assert conn.execute("SELECT value_minor FROM holdings").fetchone()[0] == 500000
    assert conn.execute("SELECT category FROM merchant_rules WHERE merchant='albert heijn'").fetchone()[0] == "groceries"
    assert [r[0] for r in conn.execute("SELECT name FROM people")] == ["Alex Example"]
    assert [r[0] for r in conn.execute("SELECT title FROM tasks")] == ["Renew insurance"]


def test_the_new_tables_and_columns_exist_and_the_database_is_sound(tmp_path):
    _, conn = _upgrade(tmp_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"assistant_changes", "truncation_audit"} <= tables
    assert "date_source" in {r[1] for r in conn.execute("PRAGMA table_info(finance_docs)")}
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_a_second_start_changes_nothing(tmp_path):
    path, conn = _upgrade(tmp_path)
    before = conn.execute("SELECT COUNT(*), SUM(amount_minor) FROM transactions").fetchone()[:]
    steps = conn.execute("SELECT COUNT(*) FROM _migrations").fetchone()[0]
    db.migrate(conn, ALL)
    assert conn.execute("SELECT COUNT(*), SUM(amount_minor) FROM transactions").fetchone()[:] == before
    assert conn.execute("SELECT COUNT(*) FROM _migrations").fetchone()[0] == steps
    conn.close()
    again = db.connect(path)
    db.migrate(again, ALL)
    assert again.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 4
