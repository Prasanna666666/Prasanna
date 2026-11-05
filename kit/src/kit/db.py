"""SQLite storage shared by every app: one local file per app, encrypted with SQLCipher when a key is given; each module migrates its own tables."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .module import Module


def home() -> Path:
    return Path(os.environ.get("ORBIT_HOME", Path.home() / ".orbit"))


class EncryptionError(RuntimeError):
    pass


def database_key() -> str | None:
    """The database key: from a file (Docker secret) or an env var. Never from a config file or the database itself."""
    f = os.environ.get("ORBIT_DB_KEY_FILE")
    if f:
        try:
            return Path(f).read_text().strip() or None
        except OSError as e:
            raise EncryptionError(f"Cannot read the database key file {f}: {e}") from e
    return os.environ.get("ORBIT_DB_KEY") or None


def connect(
    path: str | Path | None = None, key: str | None = None, on_open: Callable[[sqlite3.Connection], None] | None = None, timeout: float = 5.0
) -> sqlite3.Connection:
    """Open the database. With a key it is encrypted (SQLCipher: AES-256, whole file incl. indexes and WAL).

    ORBIT_REQUIRE_ENCRYPTION=1 (set in the Docker deployment) refuses to run without a key, so a missing
    secret can never silently fall back to a plain-text database."""
    if path is None:
        home().mkdir(parents=True, exist_ok=True)
        path = home() / "orbit.db"
    key = key or database_key()
    if key is None and os.environ.get("ORBIT_REQUIRE_ENCRYPTION") == "1":
        raise EncryptionError("Encryption is required but no database key was provided (ORBIT_DB_KEY_FILE / ORBIT_DB_KEY).")
    if key:
        try:
            from sqlcipher3 import dbapi2 as cipher
        except ImportError as e:
            raise EncryptionError("A key was given but sqlcipher3 is not installed: pip install sqlcipher3-binary") from e
        conn = cipher.connect(str(path), check_same_thread=False, timeout=timeout)
        conn.execute("PRAGMA key = \"x'" + _hexkey(key) + "'\"")  # raw 256-bit key; no passphrase stretching needed
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except cipher.DatabaseError as e:
            conn.close()
            raise EncryptionError("Wrong database key (or the file is not encrypted).") from e
        conn.row_factory = cipher.Row
    else:
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=timeout)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.DatabaseError as e:
            conn.close()
            raise EncryptionError("This database is encrypted: provide the key (ORBIT_DB_KEY_FILE / ORBIT_DB_KEY).") from e
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    if on_open:
        on_open(conn)
    if Path(path).exists():
        os.chmod(path, 0o600)  # owner-only, even without a container
    return conn


def encrypt_in_place(path: str | Path, key: str) -> bool:
    """Encrypt a database that is still plain text (all tables, including full-text search). The plain file is kept beside it as `<name>.unencrypted`
    until you delete it yourself; nothing is lost if this stops half way. Returns True if it converted a file, False if there was nothing to do."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        plain = sqlite3.connect(str(path))
        plain.execute("SELECT count(*) FROM sqlite_master").fetchone()
        plain.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        version = plain.execute("PRAGMA user_version").fetchone()[0]  # the export does not carry it, and a missing version would re-run every migration
        plain.close()
    except sqlite3.DatabaseError:
        return False  # already encrypted
    try:
        from sqlcipher3 import dbapi2 as cipher
    except ImportError as e:
        raise EncryptionError("sqlcipher3 is not installed, so the database cannot be encrypted.") from e
    target = path.with_name(path.name + ".encrypting")
    target.unlink(missing_ok=True)
    source = cipher.connect(str(path))
    try:
        source.execute(f"ATTACH DATABASE '{target}' AS enc KEY \"x'{_hexkey(key)}'\"")
        source.execute("SELECT sqlcipher_export('enc')")
        source.execute(f"PRAGMA enc.user_version = {int(version)}")
        source.execute("DETACH DATABASE enc")
    finally:
        source.close()
    check = cipher.connect(str(target))
    try:
        check.execute(f"PRAGMA key = \"x'{_hexkey(key)}'\"")
        copied = check.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
    finally:
        check.close()
    original = sqlite3.connect(str(path))
    try:
        expected = original.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
    finally:
        original.close()
    if copied != expected:
        target.unlink(missing_ok=True)
        raise EncryptionError("The encrypted copy did not match the original; nothing was changed.")
    path.rename(path.with_name(path.name + ".unencrypted"))
    target.rename(path)
    return True


def _hexkey(key: str) -> str:
    """Any string -> 64 hex chars (SHA-256), so a base64 key from the Keychain works unchanged."""
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()


class MigrationError(RuntimeError):
    """An upgrade of the database failed. Your data from before the upgrade is in the copy named in the message."""


def _copy_before_upgrade(conn: sqlite3.Connection) -> Path | None:
    """A full copy of the database (same encryption) taken just before it is changed, so a failed or unwanted upgrade can always be undone. None for an in-memory database."""
    file = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    if not file:
        return None
    folder = Path(file).parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"before-upgrade-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.db"
    copy = connect(target)
    try:
        conn.backup(copy)
        copy.commit()
    finally:
        copy.close()
    for old in sorted(folder.glob("before-upgrade-*.db"))[:-3]:  # keep the last three
        old.unlink(missing_ok=True)
    return target


def migrate(conn: sqlite3.Connection, modules: list[Module], after: Callable[[sqlite3.Connection], None] | None = None) -> None:
    """Bring the database up to the current schema. Each module's steps run in order and are recorded; a database that already holds data is copied first."""
    conn.execute("CREATE TABLE IF NOT EXISTS _migrations (module TEXT PRIMARY KEY, version INTEGER NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    have = {r["module"]: r["version"] for r in conn.execute("SELECT module, version FROM _migrations")}
    pending = [m for m in modules if len(m.migrations) > have.get(m.name, 0)]
    saved = _copy_before_upgrade(conn) if pending and have else None
    for m in pending:
        done = have.get(m.name, 0)
        for i, sql in enumerate(m.migrations[done:], start=done + 1):
            try:
                conn.executescript(sql)
            except sqlite3.Error as exc:
                raise MigrationError(
                    f"Upgrading '{m.name}' to version {i} failed ({type(exc).__name__})." + (f" Your data from before is safe in {saved}." if saved else "")
                ) from exc
            conn.execute("INSERT OR REPLACE INTO _migrations VALUES (?, ?)", (m.name, i))
        conn.commit()
    if after:
        after(conn)


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
    conn.commit()


def rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]
