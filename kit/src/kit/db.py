"""SQLite storage shared by every app: one local file per app, encrypted with SQLCipher when a key is given; each module migrates its own tables."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import zlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from .module import Module


def home() -> Path:
    """The data folder. A folder from the time the program was called Orbit is taken over, not copied: it is renamed once."""
    if os.environ.get("ATLAS_HOME"):
        return Path(os.environ["ATLAS_HOME"])
    new, old = Path.home() / ".atlas", Path.home() / ".orbit"
    if not new.exists() and old.is_dir():
        old.rename(new)
    return new


def adopt_old_name(new: Path, old: Path) -> None:
    """The database kept under its old name is renamed to the new one (with its journal files), only when the new name does not exist yet."""
    if new.exists() or not old.exists():
        return
    for suffix in ("", "-wal", "-shm", "-journal"):
        if Path(str(old) + suffix).exists():
            Path(str(old) + suffix).rename(Path(str(new) + suffix))


class EncryptionError(RuntimeError):
    pass


def database_key() -> str | None:
    """The database key: from a file (Docker secret) or an env var. Never from a config file or the database itself."""
    f = os.environ.get("ATLAS_DB_KEY_FILE")
    if f:
        try:
            return Path(f).read_text().strip() or None
        except OSError as e:
            raise EncryptionError(f"Cannot read the database key file {f}: {e}") from e
    return os.environ.get("ATLAS_DB_KEY") or None


def connect(
    path: str | Path | None = None, key: str | None = None, on_open: Callable[[sqlite3.Connection], None] | None = None, timeout: float = 5.0
) -> sqlite3.Connection:
    """Open the database. With a key it is encrypted (SQLCipher: AES-256, whole file incl. indexes and WAL).

    ATLAS_REQUIRE_ENCRYPTION=1 (set in the Docker deployment) refuses to run without a key, so a missing
    secret can never silently fall back to a plain-text database."""
    if path is None:
        home().mkdir(parents=True, exist_ok=True)
        path = home() / "finance.db"
        adopt_old_name(path, home() / "orbit.db")
    key = key or database_key()
    if key is None and os.environ.get("ATLAS_REQUIRE_ENCRYPTION") == "1":
        raise EncryptionError("Encryption is required but no database key was provided (ATLAS_DB_KEY_FILE / ATLAS_DB_KEY).")
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
            raise EncryptionError("This database is encrypted: provide the key (ATLAS_DB_KEY_FILE / ATLAS_DB_KEY).") from e
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    if on_open:
        on_open(conn)
    if Path(path).exists():
        os.chmod(path, 0o600)  # owner-only, even without a container
    return conn


KEEP_PLAIN_ENV = "ATLAS_KEEP_PLAINTEXT"  # set to 1 to keep the plain-text file beside the encrypted one after a verified conversion (off by default)
SCRUB_CHUNK = 1 << 20
_SIDECARS = ("-wal", "-shm", "-journal")


def _fingerprint(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    """Per table: how many rows and an order-independent checksum of every row, so two files can be compared by content, not by the number of tables."""
    out: dict[str, tuple[int, int]] = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        count = total = 0
        for row in conn.execute(f'SELECT * FROM "{name.replace(chr(34), chr(34) * 2)}"'):
            count += 1
            total = (total + zlib.crc32(repr(tuple(row)).encode())) & 0xFFFFFFFFFFFFFFFF
        out[name] = (count, total)
    return out


def _open_encrypted(path: Path, key: str):
    from sqlcipher3 import dbapi2 as cipher

    conn = cipher.connect(str(path))
    conn.execute(f"PRAGMA key = \"x'{_hexkey(key)}'\"")
    return conn


def _verified(path: Path, key: str, want: dict[str, tuple[int, int]], version: int) -> bool:
    """True only if the file opens with the key, passes SQLite's integrity check and holds exactly the rows and version the original held."""
    try:
        conn = _open_encrypted(path, key)
    except Exception:  # noqa: BLE001 (any failure to open means: not verified)
        return False
    try:
        return (
            conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            and conn.execute("PRAGMA user_version").fetchone()[0] == version
            and _fingerprint(conn) == want
        )
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()


def _scrub(path: Path) -> None:
    """Overwrite a plain-text file with zeros, then delete it (and its journal files). On an SSD or APFS this cannot promise the old blocks are gone; full-disk encryption (FileVault) does."""
    for file in (path, *(Path(str(path) + s) for s in _SIDECARS)):
        if not file.is_file():
            continue
        size = file.stat().st_size
        with open(file, "r+b") as handle:
            for _ in range(0, size, SCRUB_CHUNK):
                handle.write(bytes(min(SCRUB_CHUNK, size - handle.tell())))
            handle.flush()
            os.fsync(handle.fileno())
        file.unlink()


def _finish_interrupted(path: Path, key: str) -> None:
    """A conversion that stopped between its two renames leaves no database under its own name: bring back whichever copy is complete."""
    held, target = path.with_name(path.name + ".unencrypted"), path.with_name(path.name + ".encrypting")
    if path.exists() or not (held.exists() or target.exists()):
        return
    if held.exists():
        plain = sqlite3.connect(str(held))
        try:
            want, version = _fingerprint(plain), plain.execute("PRAGMA user_version").fetchone()[0]
        finally:
            plain.close()
        if target.exists() and _verified(target, key, want, version):
            target.rename(path)
            _retire(held)
        else:
            target.unlink(missing_ok=True)
            held.rename(path)  # the plain file is the only complete copy: it goes back, and the next open converts again
    elif _open_ok(target, key):
        target.rename(path)


def _retire(held: Path) -> None:
    """The plain file of a conversion that checked out: overwritten and deleted, or kept only when ATLAS_KEEP_PLAINTEXT=1 asks for it."""
    for side in _SIDECARS:
        Path(str(held) + side).unlink(missing_ok=True)
    if os.environ.get(KEEP_PLAIN_ENV) != "1":
        _scrub(held)


def _open_ok(path: Path, key: str) -> bool:
    try:
        conn = _open_encrypted(path, key)
    except Exception:  # noqa: BLE001
        return False
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()


def encrypt_in_place(path: str | Path, key: str) -> bool:
    """Encrypt a database that is still plain text (all tables, including full-text search).

    The encrypted copy is built beside it and checked against the original by content (every table's rows, the integrity check, the version) before
    anything is replaced; after the swap the file under the real name is checked again. Only then is the plain file overwritten and deleted, unless
    ATLAS_KEEP_PLAINTEXT=1 asks to keep it as `<name>.unencrypted`. If anything fails the original is left as it was. Returns True if it converted a
    file, False if there was nothing to do."""
    path = Path(path)
    try:
        import sqlcipher3  # noqa: F401
    except ImportError as e:
        raise EncryptionError("sqlcipher3 is not installed, so the database cannot be encrypted.") from e
    with _exclusive(path):  # two programs opening the same file at once must not both convert it
        return _encrypt_locked(path, key)


@contextlib.contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    """One conversion at a time per database file (a lock file beside it; where the system has no file locks, no lock)."""
    try:
        import fcntl
    except ImportError:
        yield
        return
    with open(path.with_name(path.name + ".lock"), "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _retire_redundant_copy(path: Path, key: str) -> None:
    """A plain copy left beside an encrypted file that holds exactly the same rows (a conversion that stopped before the plain file was removed) is overwritten and deleted. A plain copy that
    differs (an older leftover, or a copy kept on purpose) is never touched: it may be the only one."""
    held = path.with_name(path.name + ".unencrypted")
    if not held.is_file() or not path.is_file() or os.environ.get(KEEP_PLAIN_ENV) == "1":
        return
    try:
        plain = sqlite3.connect(str(held))
        try:
            want, version = _fingerprint(plain), plain.execute("PRAGMA user_version").fetchone()[0]
        finally:
            plain.close()
    except sqlite3.DatabaseError:
        return
    if _verified(path, key, want, version):
        _retire(held)


PLAIN_SUFFIX = ".unencrypted"


def leftover_plain_copies(folder: str | Path) -> list[Path]:
    """The plain-text copies an earlier release left beside encrypted databases."""
    return sorted(Path(folder).glob(f"*{PLAIN_SUFFIX}"))


def _same_rows(held: Path, path: Path, key: str) -> bool | None:
    """True when the plain copy and the encrypted file hold exactly the same rows, False when they differ, None when either cannot be read."""
    try:
        plain = sqlite3.connect(str(held))
        try:
            want, version = _fingerprint(plain), plain.execute("PRAGMA user_version").fetchone()[0]
        finally:
            plain.close()
    except sqlite3.DatabaseError:
        return None
    if _verified(path, key, want, version):
        return True
    return False if _open_ok(path, key) else None


def retire_leftover(held: str | Path, key: str, confirm: Callable[[str], bool] | None = None) -> str:
    """Remove one leftover plain copy, safely. An identical copy is removed at once. A copy whose rows differ from the encrypted file (it may be the only copy of older data) is removed only
    if `confirm` is given and the owner says yes to it. Nothing is removed when the encrypted file is missing or does not open with this key, or when the copy cannot be read.
    Returns what happened, in a sentence."""
    held = Path(held)
    path = held.with_name(held.name.removesuffix(PLAIN_SUFFIX))
    if not path.is_file():
        return f"kept {held.name}: the encrypted file it belongs to is missing"
    same = _same_rows(held, path, key)
    if same is None:
        return f"kept {held.name}: it cannot be read, or the encrypted file does not open with this key"
    if same:
        _retire(held)
        return f"removed {held.name}: identical to the encrypted file"
    question = f"{held.name} holds different rows from the encrypted file, so it may be the only copy of older data. Overwrite and delete it?"
    if confirm is not None and confirm(question):
        _retire(held)
        return f"removed {held.name}: you confirmed"
    return f"kept {held.name}: its rows differ from the encrypted file and you did not confirm"


def _encrypt_locked(path: Path, key: str) -> bool:
    _finish_interrupted(path, key)
    _retire_redundant_copy(path, key)
    held, target = path.with_name(path.name + ".unencrypted"), path.with_name(path.name + ".encrypting")
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        plain = sqlite3.connect(str(path))
        plain.execute("SELECT count(*) FROM sqlite_master").fetchone()
        plain.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        version = plain.execute("PRAGMA user_version").fetchone()[0]  # the export does not carry it, and a missing version would re-run every migration
        want = _fingerprint(plain)
        plain.close()
    except sqlite3.DatabaseError:
        return False  # already encrypted
    _export(path, target, key, version)
    if not _verified(target, key, want, version):
        target.unlink(missing_ok=True)
        raise EncryptionError("The encrypted copy did not match the original; nothing was changed.")
    _scrub(held)  # a plain copy left by an earlier conversion holds older data than the file being converted now
    path.rename(held)
    target.rename(path)
    if not _verified(path, key, want, version):
        path.unlink(missing_ok=True)
        held.rename(path)
        raise EncryptionError("The encrypted file did not check out after the swap; the original was put back.")
    _retire(held)
    return True


def _export(path: Path, target: Path, key: str, version: int) -> None:
    """Write an encrypted copy of the plain database next to it (the original is only read)."""
    from sqlcipher3 import dbapi2 as cipher

    target.unlink(missing_ok=True)
    source = cipher.connect(str(path))
    try:
        source.execute(f"ATTACH DATABASE '{target}' AS enc KEY \"x'{_hexkey(key)}'\"")
        source.execute("SELECT sqlcipher_export('enc')")
        source.execute(f"PRAGMA enc.user_version = {int(version)}")
        source.execute("DETACH DATABASE enc")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        source.close()


def _hexkey(key: str) -> str:
    """Any string -> 64 hex chars (SHA-256), so a base64 key from the Keychain works unchanged."""
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()


class MigrationError(RuntimeError):
    """An upgrade of the database failed. Your data from before the upgrade is in the copy named in the message."""


def copy_before_upgrade(conn: sqlite3.Connection) -> Path | None:
    """A full copy of the database (same encryption) taken just before it is changed, so a failed or unwanted upgrade can always be undone. None for an in-memory database."""
    file = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    if not file:
        return None
    folder = Path(file).parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"before-upgrade-{datetime.now(UTC):%Y%m%dT%H%M%S}.db"
    copy = connect(target)
    try:
        conn.backup(copy)
        copy.commit()
    finally:
        copy.close()
    for old in sorted(folder.glob("before-upgrade-*.db"))[:-3]:  # keep the last three
        old.unlink(missing_ok=True)
    return target


def _statements(script: str) -> list[str]:
    """The script cut into whole statements (a trigger body with its own semicolons stays in one piece)."""
    found, current = [], ""
    for line in script.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            found.append(current)
            current = ""
    if current.strip():
        found.append(current)
    return found


def _run_step(conn: sqlite3.Connection, module: str, number: int, sql: str) -> None:
    """One migration step and the note that it was applied, in one transaction: either both happen or neither does, so a failed step can simply be retried."""
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in _statements(sql):
            conn.execute(statement)
        conn.execute("INSERT OR REPLACE INTO _migrations VALUES (?, ?)", (module, number))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def migrate(conn: sqlite3.Connection, modules: list[Module], after: Callable[[sqlite3.Connection], None] | None = None) -> None:
    """Bring the database up to the current schema. Each module's steps run in order, each as one transaction with its record; a database that already holds data is copied first."""
    conn.execute("CREATE TABLE IF NOT EXISTS _migrations (module TEXT PRIMARY KEY, version INTEGER NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    have = {r["module"]: r["version"] for r in conn.execute("SELECT module, version FROM _migrations")}
    pending = [m for m in modules if len(m.migrations) > have.get(m.name, 0)]
    saved = copy_before_upgrade(conn) if pending and have else None
    for m in pending:
        done = have.get(m.name, 0)
        for i, sql in enumerate(m.migrations[done:], start=done + 1):
            try:
                _run_step(conn, m.name, i, sql)
            except sqlite3.Error as exc:
                raise MigrationError(
                    f"Upgrading '{m.name}' to version {i} failed ({type(exc).__name__})." + (f" Your data from before is safe in {saved}." if saved else "")
                ) from exc
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
