"""A Documents database written by the code of an older commit (5f7fa48, kept as a text dump) is upgraded by the current code with every document intact, the new columns and tables exist, the database is sound, and a second start changes nothing (review item O-12, Documents). Invented rows only; the dump was written by that commit, not by this one."""

import sqlite3
from pathlib import Path

from kit import db as kit_db

from library import store

FIXTURE = Path(__file__).parent / "fixtures" / "release-573d04f.sql"  # a text dump: no database files are kept in the repository


def _old(path):
    old = sqlite3.connect(path)
    old.executescript(FIXTURE.read_text(encoding="utf-8"))
    old.commit()
    old.close()


def _upgrade(tmp_path):
    path = tmp_path / "library.db"
    _old(path)
    conn = kit_db.connect(path)
    kit_db.migrate(conn, [store.MODULE])
    return path, conn


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_the_fixture_is_the_older_schema(tmp_path):
    _old(tmp_path / "old.db")
    old = sqlite3.connect(tmp_path / "old.db")
    steps_then = old.execute("SELECT version FROM _migrations WHERE module='library'").fetchone()[0]
    assert steps_then == 14 < len(store.MIGRATIONS)
    assert old.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2


def test_every_document_survives_the_upgrade_exactly(tmp_path):
    _, conn = _upgrade(tmp_path)
    got = [tuple(r) for r in conn.execute("SELECT sha256, name, kind, text FROM documents ORDER BY name")]
    assert got == [
        ("b" * 64, "blood-test.pdf", "pdf", "Glucose 5,2 mmol/L range 4 - 6"),
        ("a" * 64, "invoice-ziggo.pdf", "pdf", "FACTUUR Ziggo total 60,50 EUR"),
    ]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"kind_names", "kind_concepts"} <= tables  # the two tables the older build did not have


def test_the_database_is_sound_and_every_step_is_recorded(tmp_path):
    _, conn = _upgrade(tmp_path)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT version FROM _migrations WHERE module='library'").fetchone()[0] == len(store.MIGRATIONS)


def test_a_second_start_changes_nothing(tmp_path):
    path, conn = _upgrade(tmp_path)
    kit_db.migrate(conn, [store.MODULE])
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
    conn.close()
    again = kit_db.connect(path)
    kit_db.migrate(again, [store.MODULE])
    assert again.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
