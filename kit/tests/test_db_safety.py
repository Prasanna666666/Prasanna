"""Encrypting an existing database and upgrading a schema never lose or half-change the person's data."""

import sqlite3
from pathlib import Path

import pytest

from kit import db
from kit.module import Module

KEY = "a-test-key"


def _plain(path: Path, rows: int = 50) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany("INSERT INTO t (body) VALUES (?)", [(f"private {i}",) for i in range(rows)])
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()


def _leftovers(path: Path) -> list[str]:
    return sorted(p.name for p in path.parent.iterdir() if p.name != path.name and not p.name.startswith("backups") and not p.name.endswith(".lock"))


def test_a_plain_database_is_converted_and_no_plain_copy_remains(tmp_path):
    path = tmp_path / "a.db"
    _plain(path)
    assert db.encrypt_in_place(path, KEY) is True
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(path).execute("SELECT count(*) FROM sqlite_master").fetchone()
    conn = db.connect(path, KEY)
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 50
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    conn.close()
    assert _leftovers(path) == []
    assert b"private 1" not in path.read_bytes()


def test_the_plain_copy_is_kept_only_when_asked(tmp_path, monkeypatch):
    path = tmp_path / "a.db"
    _plain(path)
    monkeypatch.setenv(db.KEEP_PLAIN_ENV, "1")
    db.encrypt_in_place(path, KEY)
    kept = path.with_name("a.db.unencrypted")
    assert kept.is_file()
    assert sqlite3.connect(kept).execute("SELECT count(*) FROM t").fetchone()[0] == 50


def test_nothing_to_do_for_a_missing_empty_or_already_encrypted_file(tmp_path):
    assert db.encrypt_in_place(tmp_path / "none.db", KEY) is False
    (tmp_path / "empty.db").write_bytes(b"")
    assert db.encrypt_in_place(tmp_path / "empty.db", KEY) is False
    path = tmp_path / "a.db"
    _plain(path)
    db.encrypt_in_place(path, KEY)
    assert db.encrypt_in_place(path, KEY) is False


def test_the_wrong_key_is_refused(tmp_path):
    path = tmp_path / "a.db"
    _plain(path)
    db.encrypt_in_place(path, KEY)
    with pytest.raises(db.EncryptionError):
        db.connect(path, "another-key")


def test_a_failed_copy_leaves_the_original_untouched(tmp_path, monkeypatch):
    path = tmp_path / "a.db"
    _plain(path)
    before = path.read_bytes()
    monkeypatch.setattr(db, "_verified", lambda *a, **k: False)  # the encrypted copy does not match
    with pytest.raises(db.EncryptionError):
        db.encrypt_in_place(path, KEY)
    assert path.read_bytes() == before
    assert _leftovers(path) == []


def test_a_failed_check_after_the_swap_puts_the_original_back(tmp_path, monkeypatch):
    path = tmp_path / "a.db"
    _plain(path)
    before = path.read_bytes()
    calls = iter([True, False])
    monkeypatch.setattr(db, "_verified", lambda *a, **k: next(calls))
    with pytest.raises(db.EncryptionError):
        db.encrypt_in_place(path, KEY)
    assert path.read_bytes() == before


def test_a_conversion_that_stopped_between_the_renames_is_finished_or_undone(tmp_path):
    path = tmp_path / "a.db"
    _plain(path)
    held, target = path.with_name("a.db.unencrypted"), path.with_name("a.db.encrypting")
    path.rename(held)  # stopped here: no encrypted copy yet -> the plain file must come back
    assert db.encrypt_in_place(path, KEY) is True
    assert db.connect(path, KEY).execute("SELECT count(*) FROM t").fetchone()[0] == 50
    assert not held.exists()
    assert not target.exists()


def test_an_interrupted_conversion_with_a_complete_encrypted_copy_is_finished(tmp_path, monkeypatch):
    path = tmp_path / "a.db"
    _plain(path)
    monkeypatch.setenv(db.KEEP_PLAIN_ENV, "1")
    db.encrypt_in_place(path, KEY)  # leaves a.db (encrypted) and a.db.unencrypted
    held, target = path.with_name("a.db.unencrypted"), path.with_name("a.db.encrypting")
    path.rename(target)  # stopped after the first rename
    monkeypatch.delenv(db.KEEP_PLAIN_ENV)
    db.encrypt_in_place(path, KEY)
    assert db.connect(path, KEY).execute("SELECT count(*) FROM t").fetchone()[0] == 50
    assert not held.exists()


def test_a_corrupted_encrypted_copy_is_never_installed(tmp_path):
    path = tmp_path / "a.db"
    _plain(path)
    held, target = path.with_name("a.db.unencrypted"), path.with_name("a.db.encrypting")
    path.rename(held)
    target.write_bytes(b"not a database" * 100)
    db.encrypt_in_place(path, KEY)
    assert db.connect(path, KEY).execute("SELECT count(*) FROM t").fetchone()[0] == 50


def test_encryption_that_cannot_run_is_an_error_not_a_plain_fallback(tmp_path, monkeypatch):
    import builtins

    real = builtins.__import__

    def refuse(name, *a, **k):
        if name.startswith("sqlcipher3"):
            raise ImportError(name)
        return real(name, *a, **k)

    path = tmp_path / "a.db"
    _plain(path)
    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(db.EncryptionError):
        db.encrypt_in_place(path, KEY)
    monkeypatch.setenv("ATLAS_REQUIRE_ENCRYPTION", "1")
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    monkeypatch.delenv("ATLAS_DB_KEY_FILE", raising=False)
    with pytest.raises(db.EncryptionError):
        db.connect(tmp_path / "b.db")


GOOD = "CREATE TABLE a (id INTEGER PRIMARY KEY, v TEXT);\nINSERT INTO a (v) VALUES ('kept');"
HALF = "CREATE TABLE b (id INTEGER PRIMARY KEY);\nINSERT INTO b VALUES (1);\nINSERT INTO nowhere VALUES (1);"
FIXED = "CREATE TABLE IF NOT EXISTS b (id INTEGER PRIMARY KEY);\nINSERT OR IGNORE INTO b VALUES (1);"
TRIGGER = "CREATE TABLE c (id INTEGER PRIMARY KEY, n INTEGER);\nCREATE TRIGGER c_new AFTER INSERT ON c BEGIN\n  UPDATE c SET n = 1 WHERE id = NEW.id;\nEND;"


def test_a_migration_that_fails_halfway_changes_nothing_and_can_be_retried(tmp_path):
    conn = db.connect(tmp_path / "m.db")
    db.migrate(conn, [Module("m", (GOOD,))])
    with pytest.raises(db.MigrationError):
        db.migrate(conn, [Module("m", (GOOD, HALF))])
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='b'").fetchone()[0] == 0  # no half-made table
    assert conn.execute("SELECT version FROM _migrations WHERE module='m'").fetchone()[0] == 1
    assert not conn.in_transaction
    db.migrate(conn, [Module("m", (GOOD, FIXED))])  # a corrected step runs from where it stopped
    assert conn.execute("SELECT version FROM _migrations WHERE module='m'").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM b").fetchone()[0] == 1
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_a_restart_after_a_failure_sees_the_old_version(tmp_path):
    path = tmp_path / "m.db"
    conn = db.connect(path)
    db.migrate(conn, [Module("m", (GOOD,))])
    with pytest.raises(db.MigrationError):
        db.migrate(conn, [Module("m", (GOOD, HALF))])
    conn.close()
    again = db.connect(path)
    assert again.execute("SELECT version FROM _migrations WHERE module='m'").fetchone()[0] == 1
    assert again.execute("SELECT count(*) FROM sqlite_master WHERE name='b'").fetchone()[0] == 0
    assert list((tmp_path / "backups").glob("before-upgrade-*.db"))  # the copy taken before the upgrade is still there


def test_statements_with_triggers_are_kept_whole(tmp_path):
    conn = db.connect(tmp_path / "m.db")
    db.migrate(conn, [Module("m", (TRIGGER,))])
    conn.execute("INSERT INTO c (id, n) VALUES (1, 0)")
    assert conn.execute("SELECT n FROM c").fetchone()[0] == 1


def test_every_step_of_a_long_history_upgrades_from_each_old_version(tmp_path):
    steps = tuple(f"CREATE TABLE s{i} (id INTEGER PRIMARY KEY);" for i in range(5))
    for old in range(5):
        conn = db.connect(tmp_path / f"v{old}.db")
        db.migrate(conn, [Module("m", steps[:old])]) if old else None
        db.migrate(conn, [Module("m", steps)])
        assert conn.execute("SELECT version FROM _migrations WHERE module='m'").fetchone()[0] == 5
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert len(conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 's_'").fetchall()) == 5


def test_a_semicolon_inside_a_string_or_a_comment_does_not_split_a_statement(tmp_path):
    script = "CREATE TABLE s (id INTEGER PRIMARY KEY, v TEXT);\n-- a comment; with a semicolon\nINSERT INTO s (v) VALUES ('a;b;c');\nINSERT INTO s (v) VALUES ('it''s; fine');"
    conn = db.connect(tmp_path / "m.db")
    db.migrate(conn, [Module("m", (script,))])
    assert [r[0] for r in conn.execute("SELECT v FROM s ORDER BY id")] == ["a;b;c", "it's; fine"]


def test_two_programs_converting_the_same_database_at_once_end_with_one_good_encrypted_file(tmp_path):
    import threading

    path = tmp_path / "a.db"
    _plain(path, rows=2000)
    errors: list[BaseException] = []

    def convert():
        try:
            db.encrypt_in_place(path, KEY)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=convert) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    conn = db.connect(path, KEY)
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 2000
    conn.close()
    assert _leftovers(path) == []
