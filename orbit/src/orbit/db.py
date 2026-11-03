"""SQLite storage. Everything lives in one local file; each module migrates its own tables."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .module import Module


def home() -> Path:
    return Path(os.environ.get("ORBIT_HOME", Path.home() / ".orbit"))


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    if path is None:
        home().mkdir(parents=True, exist_ok=True)
        path = home() / "orbit.db"
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


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


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
    conn.commit()


def rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]
