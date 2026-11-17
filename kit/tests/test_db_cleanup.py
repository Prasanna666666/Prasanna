"""Removing the plain-text copies an older release left behind never destroys the only copy: identical copies go at once, a different one only on the owner's yes, and nothing when it cannot be checked."""

import sqlite3
from pathlib import Path

import pytest

from kit import cleanup, db

KEY = "cleanup-key"


def _pair(folder: Path, name: str = "a.db") -> tuple[Path, Path]:
    """An encrypted database and the plain copy an older release left beside it (same rows)."""
    path = folder / name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany("INSERT INTO t (body) VALUES (?)", [(f"secret {i}",) for i in range(20)])
    conn.commit()
    conn.close()
    import os

    os.environ[db.KEEP_PLAIN_ENV] = "1"
    try:
        db.encrypt_in_place(path, KEY)
    finally:
        del os.environ[db.KEEP_PLAIN_ENV]
    return path, path.with_name(name + ".unencrypted")


def _change_encrypted(path: Path) -> None:
    conn = db.connect(path, KEY)
    conn.execute("INSERT INTO t (body) VALUES ('written after the conversion')")
    conn.commit()
    conn.close()


def test_an_identical_copy_is_removed_without_asking(tmp_path):
    _path, held = _pair(tmp_path)
    assert db.retire_leftover(held, KEY).startswith("removed") and not held.exists()


def test_a_different_copy_is_kept_unless_the_owner_confirms(tmp_path):
    path, held = _pair(tmp_path)
    _change_encrypted(path)
    assert db.retire_leftover(held, KEY).startswith("kept") and held.exists()
    asked = []
    assert db.retire_leftover(held, KEY, lambda q: asked.append(q) or False).startswith("kept") and held.exists() and "only copy" in asked[0]
    assert db.retire_leftover(held, KEY, lambda q: True).startswith("removed") and not held.exists()


def test_nothing_is_removed_when_the_encrypted_file_is_missing_or_the_key_is_wrong(tmp_path):
    path, held = _pair(tmp_path)
    assert db.retire_leftover(held, "another-key", lambda q: True).startswith("kept") and held.exists()
    path.unlink()
    assert "missing" in db.retire_leftover(held, KEY, lambda q: True) and held.exists()


def test_a_copy_that_cannot_be_read_is_kept(tmp_path):
    _path, held = _pair(tmp_path)
    held.write_bytes(b"not a database" * 50)
    assert db.retire_leftover(held, KEY, lambda q: True).startswith("kept") and held.exists()


def test_the_command_removes_identical_copies_and_asks_about_the_others(tmp_path, monkeypatch, capsys):
    one, held_one = _pair(tmp_path, "one.db")
    two, held_two = _pair(tmp_path, "two.db")
    _change_encrypted(two)
    monkeypatch.setenv("ATLAS_DB_KEY", KEY)
    answers = iter(["no"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cleanup.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert not held_one.exists() and held_two.exists()
    assert "removed one.db.unencrypted" in out and "kept two.db.unencrypted" in out
    assert one.exists() and two.exists()


def test_the_command_does_nothing_without_a_key(tmp_path, monkeypatch, capsys):
    _path, held = _pair(tmp_path)
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    monkeypatch.delenv("ATLAS_DB_KEY_FILE", raising=False)
    assert cleanup.main([str(tmp_path)]) == 1 and held.exists()
    assert "nothing was removed" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["yes", "YES "])
def test_only_yes_confirms_a_different_copy(tmp_path, monkeypatch, answer):
    path, held = _pair(tmp_path)
    _change_encrypted(path)
    monkeypatch.setenv("ATLAS_DB_KEY", KEY)
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)
    cleanup.main([str(tmp_path)])
    assert not held.exists()
