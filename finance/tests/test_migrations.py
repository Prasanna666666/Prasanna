import dataclasses
import sqlite3

import pytest

from finance import db
from finance.modules import ALL


def old_version(modules, keep):
    """The app as it was when each module had only its first `keep` migrations."""
    return [dataclasses.replace(m, migrations=m.migrations[:keep]) for m in modules]


def test_an_old_database_is_upgraded_in_place_and_keeps_its_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    conn = db.connect()
    db.migrate(conn, old_version(ALL, 1))
    conn.execute("INSERT INTO transactions (day, amount_minor, kind, category, note) VALUES ('2026-01-05', 1234, 'expense', 'food', 'old payment')")
    conn.commit()
    db.migrate(conn, ALL)  # the new version of the app starts
    assert conn.execute("SELECT amount_minor, note FROM transactions").fetchone()[:] == (1234, "old payment")
    versions = {r["module"]: r["version"] for r in conn.execute("SELECT * FROM _migrations")}
    assert versions["money"] == len(next(m for m in ALL if m.name == "money").migrations)
    saved = list((tmp_path / "backups").glob("before-upgrade-*.db"))
    assert len(saved) == 1
    copy = sqlite3.connect(saved[0])
    assert copy.execute("SELECT note FROM transactions").fetchone()[0] == "old payment"  # the copy is the database as it was before the upgrade
    assert "eur_minor" not in [r[1] for r in copy.execute("PRAGMA table_info(transactions)")]


def test_a_fresh_database_and_an_up_to_date_one_make_no_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    conn = db.connect()
    db.migrate(conn, ALL)
    db.migrate(conn, ALL)
    assert not list((tmp_path / "backups").glob("before-upgrade-*.db")) if (tmp_path / "backups").exists() else True


def test_a_failing_upgrade_says_where_the_safe_copy_is(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    conn = db.connect()
    db.migrate(conn, old_version(ALL, 1))
    broken = [dataclasses.replace(m, migrations=(*m.migrations, "ALTER TABLE no_such_table ADD COLUMN x TEXT;")) if m.name == "tasks" else m for m in ALL]
    with pytest.raises(db.MigrationError, match="safe in"):
        db.migrate(conn, broken)
