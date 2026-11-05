"""SQLite storage. Everything lives in one local file; each module migrates its own tables."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
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
    """`ledger` = the payments the reports read. By default ONE currency, shown as it is (the main currency until you pick another), so euros and rupees are
    never added together. 'ALL' is the option to convert everything to euros at the rate of each payment's day. Payments with no currency recorded count as
    the main currency. A per-connection view over `transactions`; every report reads it. `native_minor` is always the amount in the payment's own currency."""
    main = "COALESCE((SELECT value FROM main.settings WHERE key='currency'), 'EUR')"
    viewed = f"COALESCE((SELECT value FROM main.settings WHERE key='view_currency'), {main})"
    try:
        conn.execute("DROP VIEW IF EXISTS temp.ledger")
        columns = [r[1] for r in conn.execute("PRAGMA main.table_info(transactions)")]
        plain = "*, amount_minor AS native_minor"
        if "eur_minor" in columns:
            # 'ALL' = everything in euros at the rate of its own day; a payment that could not be converted is left out and reported, never guessed
            everything = ", ".join("eur_minor AS amount_minor" if c == "amount_minor" else c for c in columns) + ", amount_minor AS native_minor"
            conn.execute(
                f"CREATE TEMP VIEW ledger AS SELECT {everything} FROM main.transactions WHERE {viewed} = 'ALL' AND eur_minor IS NOT NULL "
                f"UNION ALL SELECT {plain} FROM main.transactions WHERE {viewed} = 'ALL' AND eur_minor IS NULL AND COALESCE(NULLIF(currency, ''), {main}) = 'EUR' "
                f"UNION ALL SELECT {plain} FROM main.transactions WHERE {viewed} <> 'ALL' AND COALESCE(NULLIF(currency, ''), {main}) = {viewed}"
            )
        else:
            conn.execute(
                f"CREATE TEMP VIEW ledger AS SELECT {plain} FROM main.transactions WHERE {viewed} <> 'ALL' AND COALESCE(NULLIF(currency, ''), {main}) = {viewed}"
            )
    except sqlite3.Error:
        pass  # before the first migration there is nothing to view


def view_currency(conn: sqlite3.Connection) -> str:
    """One currency, shown as it is (the default: your main currency), or 'ALL' = everything converted to euros."""
    return get_setting(conn, "view_currency", "") or get_setting(conn, "currency", "EUR")


def display_currency(conn: sqlite3.Connection) -> str:
    """The currency the amounts on screen are in."""
    v = view_currency(conn)
    return "EUR" if v == "ALL" else v


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


def migrate(conn: sqlite3.Connection, modules: list[Module]) -> None:
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
    ledger_view(conn)


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
    conn.commit()


def rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]
