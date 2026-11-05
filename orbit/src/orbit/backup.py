"""A daily backup of the database (it stays encrypted: the copy is made through the same key) and a check that the database itself is intact.
Backups live next to the database, so they protect against a mistake or a damaged file, not against losing the disk: copy the folder somewhere safe too."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import clock, db, log
from .findings import Finding


def integrity(conn) -> str:
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    except sqlite3.Error as e:
        return f"{type(e).__name__}: {e}"


def daily(conn, directory: Path | None = None, keep: int = 7, today: date | None = None) -> list[Finding]:
    """Make today's backup if there is none, prune old ones, and report. Never raises."""
    directory = directory or (db.home() / "backups")
    today = today or clock.today()
    found = []
    state = integrity(conn)
    found.append(
        Finding(
            "integrity",
            "ok" if state == "ok" else "fail",
            "database",
            "the database is intact" if state == "ok" else f"the database reports a problem: {state[:120]}",
        )
    )
    try:
        conn.commit()  # a copy is taken of a settled database: an open transaction would make the copy wait for it forever
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"orbit-{today.isoformat()}.db"
        if not target.exists():
            copy = db.connect(target)
            try:
                conn.backup(copy)
                copy.commit()
                n_src = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
                n_dst = copy.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
                ok = integrity(copy) == "ok" and n_src == n_dst
            finally:
                copy.close()
            if not ok:
                target.unlink(missing_ok=True)
                found.append(Finding("backup", "fail", "backup", "today's backup could not be verified and was discarded"))
                return found
        for old in sorted(directory.glob("orbit-*.db"))[:-keep]:
            old.unlink(missing_ok=True)
        newest = sorted(directory.glob("orbit-*.db"))[-1].stem.removeprefix("orbit-")
        age = (today - date.fromisoformat(newest)).days
        found.append(Finding("backup", "ok" if age <= 1 else "warn", "backup", f"last backup: {newest}" + ("" if age <= 1 else f" ({age} days ago)")))
    except (OSError, sqlite3.Error, ValueError, IndexError) as e:
        log.failed("backup failed", e)
        found.append(Finding("backup", "warn", "backup", f"no backup could be made ({type(e).__name__})"))
    return found


def restorable(directory: Path | None = None) -> list[str]:
    directory = directory or (db.home() / "backups")
    return [p.name for p in sorted(directory.glob("orbit-*.db"))]


def oldest_kept(today: date, keep: int = 7) -> str:
    return (today - timedelta(days=keep)).isoformat()
