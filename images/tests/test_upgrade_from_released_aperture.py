"""An index written by the released aperture code (commit 5d3ddb5 of branch aperture, the real older release, kept as a text dump of invented rows) opens with the current code: with no key it stays as it is, with a key it is encrypted in place with every row intact and no plain copy left (review item O-12, Images). The schema is the same 16 steps in both builds, so the change that matters here is the encryption."""

import sqlite3
from pathlib import Path

import pytest

from images.db import MIGRATIONS, Database

FIXTURE = (
    Path(__file__).parent / "fixtures" / "release-aperture-5d3ddb5.sql"
)  # a text dump: no database files are kept in the repository


def _released_index(path):
    old = sqlite3.connect(path)
    old.executescript(FIXTURE.read_text(encoding="utf-8"))
    old.commit()
    old.close()


def _paths(conn):
    return [r[0] for r in conn.execute("SELECT path FROM items ORDER BY id")]


def test_the_fixture_is_a_released_index(tmp_path):
    _released_index(tmp_path / "index.db")
    old = sqlite3.connect(tmp_path / "index.db")
    assert old.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert _paths(old) == ["/Photos/2026/lisbon-1.jpg", "/Photos/2026/lisbon-2.jpg", "/Photos/2026/receipt.jpg"]


def test_opened_without_a_key_it_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    _released_index(tmp_path / "index.db")
    conn = Database(tmp_path / "index.db").connect()
    assert _paths(conn) == ["/Photos/2026/lisbon-1.jpg", "/Photos/2026/lisbon-2.jpg", "/Photos/2026/receipt.jpg"]
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_opened_with_a_key_it_is_encrypted_in_place_with_every_row_intact(tmp_path, monkeypatch):
    path = tmp_path / "index.db"
    _released_index(path)
    monkeypatch.setenv("ATLAS_DB_KEY", "a-test-key")
    conn = Database(path).connect()
    assert _paths(conn) == ["/Photos/2026/lisbon-1.jpg", "/Photos/2026/lisbon-2.jpg", "/Photos/2026/receipt.jpg"]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert conn.execute("SELECT name FROM people").fetchone()[0] == "Alex Example"
    conn.close()
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(path).execute("SELECT count(*) FROM sqlite_master").fetchone()  # no longer readable without the key
    assert not path.with_name(path.name + ".unencrypted").exists()
    again = Database(path).connect()  # a second start changes nothing
    assert len(_paths(again)) == 3
