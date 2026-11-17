"""A stop at any step of turning a plain database into an encrypted one never loses the data, never reports success before the checks, and after the next start leaves one good encrypted file and no plain copy."""

import sqlite3
from pathlib import Path

import pytest

from kit import db

KEY = "crash-test-key"


def _plain(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany("INSERT INTO t (body) VALUES (?)", [(f"private row {i}",) for i in range(40)])
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()


def _boom(*_args, **_kwargs):
    raise OSError("the power went out")


def _fail_nth_rename(monkeypatch, nth: int) -> None:
    real = Path.rename
    seen = {"n": 0}

    def rename(self, target):
        seen["n"] += 1
        if seen["n"] == nth:
            raise OSError("the power went out")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", rename)


def _fail_nth_verification(monkeypatch, nth: int) -> None:
    real = db._verified
    seen = {"n": 0}

    def verified(*args, **kwargs):
        seen["n"] += 1
        if seen["n"] == nth:
            raise OSError("the power went out")
        return real(*args, **kwargs)

    monkeypatch.setattr(db, "_verified", verified)


STOPS = {
    "while copying": lambda mp: mp.setattr(db, "_export", _boom),
    "while verifying the copy": lambda mp: _fail_nth_verification(mp, 1),
    "before the original is moved aside": lambda mp: _fail_nth_rename(mp, 1),
    "between the two renames": lambda mp: _fail_nth_rename(mp, 2),
    "while verifying the swapped file": lambda mp: _fail_nth_verification(mp, 2),
    "while overwriting the plain copy": lambda mp: mp.setattr(db, "_scrub", _boom),
}


@pytest.mark.parametrize("stop", list(STOPS))
def test_a_stop_is_never_reported_as_success_and_the_next_start_leaves_one_good_encrypted_file(tmp_path, monkeypatch, stop):
    path = tmp_path / "a.db"
    _plain(path)
    with monkeypatch.context() as stopped:
        STOPS[stop](stopped)
        with pytest.raises(OSError):
            db.encrypt_in_place(path, KEY)  # it raised: it did not say "encrypted"
    # the next start, with everything working again
    assert db.encrypt_in_place(path, KEY) in (True, False)
    conn = db.connect(path, KEY)
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 40
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
    for other in tmp_path.iterdir():
        if other.name != path.name and not other.name.endswith(".lock"):
            raise AssertionError(f"a file was left behind after a stop {stop}: {other.name}")
    assert b"private row" not in path.read_bytes(), "the file is encrypted"


@pytest.mark.parametrize("stop", ["while copying", "while verifying the copy", "before the original is moved aside"])
def test_before_the_swap_the_original_is_still_the_valid_database(tmp_path, monkeypatch, stop):
    path = tmp_path / "a.db"
    _plain(path)
    before = path.read_bytes()
    with monkeypatch.context() as stopped:
        STOPS[stop](stopped)
        with pytest.raises(OSError):
            db.encrypt_in_place(path, KEY)
    assert path.read_bytes() == before
