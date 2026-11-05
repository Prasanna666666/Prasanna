"""SQLite storage: schema, versioned migrations and small helpers.

One SQLite file (WAL mode where the drive allows it) holds everything:
items, CLIP embeddings, faces, people and the FTS5 text index.  Every caller
opens its *own* connection via :meth:`Database.connect`; connections are never
shared between threads.
"""

from __future__ import annotations

import sqlite3
import threading
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

_MIGRATION_8 = """
-- What is IN each picture, read once from the stored preview (the original is never opened again).
CREATE TABLE photo_details(
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    read_at REAL NOT NULL,
    notes   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE photo_labels(          -- scene / object / landmark labels, from Apple Vision and from the image embedding
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    label   TEXT NOT NULL,
    score   REAL NOT NULL,
    source  TEXT NOT NULL
);
CREATE INDEX photo_labels_label ON photo_labels(label);
CREATE INDEX photo_labels_item  ON photo_labels(item_id);
CREATE TABLE photo_objects(         -- things with a place in the frame (animals, people, salient regions, barcodes); boxes are 0..1
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    kind    TEXT NOT NULL,
    label   TEXT NOT NULL,
    score   REAL NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL
);
CREATE INDEX photo_objects_item ON photo_objects(item_id);
CREATE TABLE photo_text(            -- every piece of text with where it sits in the frame
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    text    TEXT NOT NULL,
    score   REAL NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL
);
CREATE INDEX photo_text_item ON photo_text(item_id);
"""

_MIGRATION_9 = """
ALTER TABLE photo_details ADD COLUMN phash INTEGER;     -- 64-bit perceptual fingerprint: near-duplicates differ in few bits
CREATE INDEX photo_details_phash ON photo_details(phash);
CREATE TABLE events(                -- a trip or occasion: photos close in time (and place)
    id      INTEGER PRIMARY KEY,
    start   TEXT NOT NULL,
    stop    TEXT NOT NULL,
    n       INTEGER NOT NULL,
    place   TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT ''
);
CREATE TABLE photo_events(
    item_id  INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE
);
CREATE INDEX photo_events_event ON photo_events(event_id);
"""

_MIGRATION_10 = """
CREATE TABLE face_attributes(       -- expression and age group of each face, read from its saved crop
    face_id      INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    expression   TEXT NOT NULL,
    expression_p REAL NOT NULL,
    age          TEXT NOT NULL,
    age_p        REAL NOT NULL
);
"""

_MIGRATION_11 = """
-- Photos without GPS: a location worked out from the photos around them in time, kept ONLY where that kind of guess measured >= 95%
-- accurate on the library's own photos that do have GPS.
ALTER TABLE items ADD COLUMN gps_est_lat REAL;
ALTER TABLE items ADD COLUMN gps_est_lon REAL;
ALTER TABLE items ADD COLUMN gps_est_conf REAL;          -- measured accuracy of this kind of guess (0..1)
ALTER TABLE items ADD COLUMN gps_est_place TEXT;
ALTER TABLE items ADD COLUMN gps_est_place_text TEXT NOT NULL DEFAULT '';
"""

_MIGRATION_12 = """
CREATE TABLE photo_vision(          -- everything the vision-language model read from a picture, kept for good (one analysis per photo)
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    model   TEXT NOT NULL,
    data    TEXT NOT NULL,       -- JSON
    read_at REAL NOT NULL
);
"""

_MIGRATION_13 = """
CREATE TABLE face_ages(             -- the age model's estimate for each face, in years
    face_id INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    years   REAL NOT NULL
);
"""

_MIGRATION_14 = """
CREATE TABLE photo_venues(          -- what the vision model made of photos that look like a sports venue (one analysis per photo, kept for good)
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    data    TEXT NOT NULL,
    read_at REAL NOT NULL
);
"""

_MIGRATION_15 = """
-- Counting the faces in each photo read every face row, including its 2 KB vector, from the external drive. This index holds the three numbers
-- the count needs, so the count never touches the vectors.
CREATE INDEX IF NOT EXISTS faces_count ON faces(item_id, score, px);
"""

_MIGRATION_16 = """
-- "Every live photo" read the whole items table (wide rows) from the drive on each question. This index answers it without touching the rows.
CREATE INDEX IF NOT EXISTS items_live ON items(missing, meta_done, id);
"""

MIGRATIONS: list[str] = [
    _MIGRATION_1,
    _MIGRATION_2,
    _MIGRATION_3,
    _MIGRATION_4,
    _MIGRATION_5,
    _MIGRATION_6,
    _MIGRATION_7,
    _MIGRATION_8,
    _MIGRATION_9,
    _MIGRATION_10,
    _MIGRATION_11,
    _MIGRATION_12,
    _MIGRATION_13,
    _MIGRATION_14,
    _MIGRATION_15,
    _MIGRATION_16,
]


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
        conn.execute("PRAGMA mmap_size=268435456")  # read through the OS cache: much faster on an external drive
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
