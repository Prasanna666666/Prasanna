"""SQLite storage: schema, versioned migrations and small helpers.

One SQLite file (WAL mode where the drive allows it) holds everything:
items, CLIP embeddings, faces, people and the FTS5 text index.  Every caller
opens its *own* connection via :meth:`Database.connect`; connections are never
shared between threads.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

# --------------------------------------------------------------------------
# Migrations.  Append new entries; never edit an old one.
# `PRAGMA user_version` stores how many have been applied.
# --------------------------------------------------------------------------
_MIGRATION_1 = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE items(
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,      -- absolute path of the ORIGINAL (read-only)
    rel_path    TEXT NOT NULL DEFAULT '',
    meta_text   TEXT NOT NULL DEFAULT '',  -- lower-cased rel_path + camera + lens (path engine)
    kind        TEXT NOT NULL,             -- image | pdf | text
    size        INTEGER NOT NULL DEFAULT 0,
    mtime       REAL NOT NULL DEFAULT 0,
    width       INTEGER, height INTEGER,
    taken_at    TEXT,                      -- 'YYYY-MM-DD HH:MM:SS' (EXIF, else file date)
    camera      TEXT, lens TEXT,
    gps_lat     REAL, gps_lon REAL,
    place       TEXT,                      -- display: 'Bengaluru, India'
    place_text  TEXT NOT NULL DEFAULT '',  -- lower-cased names + alternates (place engine)
    exif_json   TEXT,
    thumb       TEXT, preview TEXT,        -- relative to the data folder
    meta_done   INTEGER NOT NULL DEFAULT 0,
    clip_done   INTEGER NOT NULL DEFAULT 0,
    faces_done  INTEGER NOT NULL DEFAULT 0,
    ocr_done    INTEGER NOT NULL DEFAULT 0,
    ocr_chars   INTEGER NOT NULL DEFAULT 0,
    error       TEXT,                      -- set when the item could not be indexed at all
    notes       TEXT,                      -- non-fatal per-stage warnings
    missing     INTEGER NOT NULL DEFAULT 0,
    indexed_at  REAL
);
CREATE INDEX items_taken ON items(taken_at);
CREATE INDEX items_live  ON items(missing, kind);

CREATE TABLE embeddings(
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    vec     BLOB NOT NULL                  -- float16, L2-normalised
);

CREATE TABLE people(
    id INTEGER PRIMARY KEY, name TEXT, hidden INTEGER NOT NULL DEFAULT 0, created_at REAL
);

CREATE TABLE faces(
    id        INTEGER PRIMARY KEY,
    item_id   INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,    -- normalised 0..1
    score     REAL NOT NULL DEFAULT 0,
    px        INTEGER NOT NULL DEFAULT 0,  -- shorter side of the face box in pixels
    emb       BLOB NOT NULL,               -- float32, L2-normalised
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    locked    INTEGER NOT NULL DEFAULT 0,  -- 1 = decided by the user, never regrouped
    crop      TEXT
);
CREATE INDEX faces_person ON faces(person_id);
CREATE INDEX faces_item   ON faces(item_id);
"""

_MIGRATION_2 = """
ALTER TABLE items ADD COLUMN sha256 TEXT;          -- content hash, filled lazily for duplicate detection
CREATE INDEX items_size ON items(size);

-- Write-ahead journal for the only operation that touches the library: moving files.
CREATE TABLE move_batches(
    id TEXT PRIMARY KEY, label TEXT NOT NULL, created REAL NOT NULL, undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE moves(
    id      INTEGER PRIMARY KEY,
    batch   TEXT NOT NULL REFERENCES move_batches(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL,
    src     TEXT NOT NULL,
    dst     TEXT NOT NULL,
    status  TEXT NOT NULL,                          -- pending | done | undone | failed
    detail  TEXT
);
CREATE INDEX moves_batch ON moves(batch);
"""

_MIGRATION_3 = """
ALTER TABLE items ADD COLUMN sharp REAL;           -- sharpness of the sharpest region (higher = sharper)
ALTER TABLE items ADD COLUMN bright REAL;          -- mean luminance 0-255
ALTER TABLE items ADD COLUMN contrast REAL;        -- luminance standard deviation

-- User decisions about photo quality.  status 'defect' = labelled bad, 'ok' = reviewed and fine.
CREATE TABLE flags(
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    status  TEXT NOT NULL,
    reason  TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
CREATE INDEX flags_status ON flags(status);
"""

_MIGRATION_4 = """
ALTER TABLE items ADD COLUMN taken_exif INTEGER NOT NULL DEFAULT 0;   -- 1 = taken_at came from the camera (not the file date)
"""

_MIGRATION_5 = """
CREATE TABLE captions(
    item_id INTEGER PRIMARY KEY,
    caption TEXT NOT NULL,
    model   TEXT NOT NULL,
    created REAL NOT NULL
);
"""

_MIGRATION_6 = """
ALTER TABLE items ADD COLUMN hue REAL;   -- dominant colour of the preview; NULL = not measured yet, -1 = unreadable
ALTER TABLE items ADD COLUMN sat REAL;
ALTER TABLE items ADD COLUMN val REAL;
"""

_MIGRATION_7 = """
-- Everything the file says about itself, read once and kept (EXIF, GPS, XMP, IPTC, colour profile, file facts, fingerprint).
CREATE TABLE file_metadata(
    item_id        INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    reader_version INTEGER NOT NULL,
    sha256         TEXT,
    data           TEXT NOT NULL,   -- JSON
    read_at        REAL NOT NULL
);
CREATE INDEX file_metadata_sha ON file_metadata(sha256);
"""

MIGRATIONS: list[str] = [_MIGRATION_1, _MIGRATION_2, _MIGRATION_3, _MIGRATION_4, _MIGRATION_5, _MIGRATION_6, _MIGRATION_7]


class Database:
    """Factory for per-caller SQLite connections."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ready = False
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=60, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":  # some drive formats cannot do WAL
                conn.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.DatabaseError:
            pass
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-65536")
        if not self._ready:
            with self._lock:
                if not self._ready:
                    self._migrate(conn)
                    self._ready = True
        return conn

    # ------------------------------------------------------------------
    def _migrate(self, conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            conn.executescript("BEGIN;\n" + script + f"\nPRAGMA user_version={number};\nCOMMIT;")
        _ensure_fts(conn)


def _ensure_fts(conn: sqlite3.Connection) -> None:
    """Create the full-text table.

    The *trigram* tokenizer gives fast **substring** search, which is what you
    want for receipt numbers and partial words ("18.40", "4417").  Very old
    SQLite builds fall back to the classic unicode61 tokenizer."""
    if meta_get(conn, "fts_tokenizer"):
        return
    for tokenizer in ("trigram", "unicode61 remove_diacritics 2"):
        try:
            conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, tokenize='{tokenizer}')")
        except sqlite3.OperationalError:
            continue
        meta_set(conn, "fts_tokenizer", tokenizer.split()[0])
        conn.commit()
        return
    raise RuntimeError("This Python's SQLite lacks FTS5. Use python.org or Homebrew Python.")


# --------------------------------------------------------------------------
# meta key/value helpers
# --------------------------------------------------------------------------
def meta_get(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))


def in_clause(values: list[int] | list[str]) -> str:
    """``?,?,?`` placeholders for an IN (...) clause."""
    return ",".join("?" * len(values))


def chunked(values: list[T], size: int = 500) -> list[list[T]]:
    """Split a list so IN (...) clauses stay under SQLite's variable limit."""
    return [values[i : i + size] for i in range(0, len(values), size)]


def run_in_transaction(conn: sqlite3.Connection, fn: Callable[[], None]) -> None:
    """Run ``fn`` and commit, or roll back if it raises."""
    try:
        fn()
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
