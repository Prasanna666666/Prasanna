"""SQLite storage. Everything lives in one local file; each module migrates its own tables."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .module import Module


def home() -> Path:
    return Path(os.environ.get("ORBIT_HOME", Path.home() / ".orbit"))


class EncryptionError(RuntimeError):
    pass


def _key() -> str | None:
    """The database key: from a file (Docker secret) or an env var. Never from a config file or the database itself."""
    f = os.environ.get("ORBIT_DB_KEY_FILE")
    if f:
        try:
            return Path(f).read_text().strip() or None
        except OSError as e:
            raise EncryptionError(f"Cannot read the database key file {f}: {e}") from e
    return os.environ.get("ORBIT_DB_KEY") or None


def connect(path: str | Path | None = None, key: str | None = None) -> sqlite3.Connection:
    """Open the database. With a key it is encrypted (SQLCipher: AES-256, whole file incl. indexes and WAL).

    ORBIT_REQUIRE_ENCRYPTION=1 (set in the Docker deployment) refuses to run without a key, so a missing
    secret can never silently fall back to a plain-text database."""
    if path is None:
        home().mkdir(parents=True, exist_ok=True)
        path = home() / "orbit.db"
    key = key or _key()
    if key is None and os.environ.get("ORBIT_REQUIRE_ENCRYPTION") == "1":
        raise EncryptionError("Encryption is required but no database key was provided (ORBIT_DB_KEY_FILE / ORBIT_DB_KEY).")
    if key:
        try:
            from sqlcipher3 import dbapi2 as cipher
        except ImportError as e:
            raise EncryptionError("A key was given but sqlcipher3 is not installed: pip install 'orbit[secure]'") from e
        conn = cipher.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA key = \"x'" + _hexkey(key) + "'\"")  # raw 256-bit key; no passphrase stretching needed
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except cipher.DatabaseError as e:
            conn.close()
            raise EncryptionError("Wrong database key (or the file is not encrypted).") from e
        conn.row_factory = cipher.Row
    else:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.DatabaseError as e:
            conn.close()
            raise EncryptionError("This database is encrypted: provide the key (ORBIT_DB_KEY_FILE / ORBIT_DB_KEY).") from e
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    ledger_view(conn)
    if Path(path).exists():
        os.chmod(path, 0o600)  # owner-only, even without a container
    return conn


def _hexkey(key: str) -> str:
    """Any string -> 64 hex chars (SHA-256), so a base64 key from the Keychain works unchanged."""
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()


def ledger_view(conn: sqlite3.Connection) -> None:
    """`ledger` = the payments of ONE currency (the one being viewed), so euros and rupees can never be added together by accident.
    Payments with no currency recorded count as the main currency. It is a per-connection view over `transactions`, read by every report."""
    main = "COALESCE((SELECT value FROM main.settings WHERE key='currency'), 'EUR')"
    viewed = f"COALESCE((SELECT value FROM main.settings WHERE key='view_currency'), {main})"
    try:
        conn.execute("DROP VIEW IF EXISTS temp.ledger")
        conn.execute(f"CREATE TEMP VIEW ledger AS SELECT * FROM main.transactions WHERE COALESCE(NULLIF(currency, ''), {main}) = {viewed}")
    except sqlite3.Error:
        pass  # before the first migration there is nothing to view


def view_currency(conn: sqlite3.Connection) -> str:
    return get_setting(conn, "view_currency", "") or get_setting(conn, "currency", "EUR")


def migrate(conn: sqlite3.Connection, modules: list[Module]) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS _migrations (module TEXT PRIMARY KEY, version INTEGER NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    for m in modules:
        row = conn.execute("SELECT version FROM _migrations WHERE module=?", (m.name,)).fetchone()
        done = row["version"] if row else 0
        for i, sql in enumerate(m.migrations[done:], start=done + 1):
            conn.executescript(sql)
            conn.execute("INSERT OR REPLACE INTO _migrations VALUES (?, ?)", (m.name, i))
        conn.commit()
    ledger_view(conn)


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
    conn.commit()


def rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]
