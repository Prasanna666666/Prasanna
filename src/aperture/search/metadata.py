"""Path / filename / camera, GPS place and date engines.

Matching is word-prefix based on folded text (``"banga"`` finds the folder
"Bangalore 2019" but ``"art"`` does not find "party"), and all query words
must match, which keeps results precise.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import numpy as np

from .textnorm import like_escape, tokens


def _ids(rows: list[tuple[int]] | list[sqlite3.Row]) -> np.ndarray:
    return np.fromiter((r[0] for r in rows), np.int64)


def _word_prefix_ids(conn: sqlite3.Connection, column: str, query: str) -> np.ndarray:
    words = tokens(query, min_len=2)
    if not words:
        return np.zeros(0, np.int64)
    cached = _text_column(conn, column)
    if cached is not None:  # in memory: the table is read from the drive once, not on every search
        ids, texts = cached
        needles = [" " + w for w in words]  # stored text starts with a space; a word may start anywhere after one
        keep = [i for i, text in enumerate(texts) if all(n in text for n in needles)]
        return ids[keep] if keep else np.zeros(0, np.int64)
    clause = " AND ".join(f"{column} LIKE ? ESCAPE '\\'" for _ in words)
    params = [f"% {like_escape(w)}%" for w in words]  # stored text starts with a space
    return _ids(conn.execute(f"SELECT id FROM items WHERE missing=0 AND {clause} ORDER BY id", params).fetchall())


def path_ids(conn: sqlite3.Connection, query: str) -> np.ndarray:
    """Folders, file names, camera and lens (``items.meta_text``)."""
    return _word_prefix_ids(conn, "meta_text", query)


def place_ids(conn: sqlite3.Connection, query: str) -> np.ndarray:
    """Cities/countries resolved offline from EXIF GPS (``items.place_text``)."""
    return _word_prefix_ids(conn, "place_text", query)


def estimated_place_ids(conn: sqlite3.Connection, query: str) -> np.ndarray:
    """Photos with no GPS whose place was worked out from the photos around them (only guesses that tested >= 80% accurate are stored)."""
    return _word_prefix_ids(conn, "gps_est_place_text", query)


def date_ids(conn: sqlite3.Connection, start: str, end: str) -> np.ndarray:
    """Photos taken in ``[start, end)`` (ISO dates)."""
    return _ids(
        conn.execute("SELECT id FROM items WHERE missing=0 AND taken_at>=? AND taken_at<? ORDER BY id", (start, end)).fetchall()
    )


def all_ids(conn: sqlite3.Connection, *, indexed_only: bool = True) -> np.ndarray:
    """Every live item (the universe for NOT-clauses and 'show everything')."""
    sql = "SELECT id FROM items WHERE missing=0" + (" AND meta_done=1" if indexed_only else "") + " ORDER BY id"
    key = _file_signature(conn, indexed_only)
    if key is not None and key in _ALL_IDS:
        return _ALL_IDS[key].copy()
    ids = _ids(conn.execute(sql).fetchall())
    if key is not None:
        _ALL_IDS.clear()  # one entry is enough: the library is the same until its file changes
        _ALL_IDS[key] = ids.copy()
    return ids


_ALL_IDS: dict[Any, np.ndarray] = {}
_MEMO: dict[Any, Any] = {}


def remembered(conn: sqlite3.Connection, name: Any, compute: Any) -> Any:
    """The answer to a whole-library question (a count, a list of positions ...), kept until the library file changes. Reading the library from
    the external drive takes seconds, and a question used to repeat it many times."""
    signature = _file_signature(conn, True)
    if signature is None:
        return compute()
    key = (name, signature)
    if key not in _MEMO:
        if len(_MEMO) > 64:
            _MEMO.clear()
        _MEMO[key] = compute()
    value = _MEMO[key]
    return value.copy() if isinstance(value, np.ndarray) else value
_TEXT: dict[str, tuple[Any, np.ndarray, list[str]]] = {}
TEXT_COLUMNS = ("meta_text", "place_text", "gps_est_place_text")


def _text_column(conn: sqlite3.Connection, column: str) -> tuple[np.ndarray, list[str]] | None:
    """(ids, lower-cased texts) of every live photo for one text column, remembered until the library file changes. None when that cannot be
    told safely (the caller then asks the database directly)."""
    if column not in TEXT_COLUMNS:
        return None
    key = _file_signature(conn, True)
    if key is None:
        return None
    hit = _TEXT.get(column)
    if hit is not None and hit[0] == key:
        return hit[1], hit[2]
    rows = conn.execute(f"SELECT id, {column} FROM items WHERE missing=0 ORDER BY id").fetchall()
    ids = np.fromiter((r[0] for r in rows), np.int64, count=len(rows))
    texts = [(r[1] or "").lower() for r in rows]
    _TEXT[column] = (key, ids, texts)
    return ids, texts


def _file_signature(conn: sqlite3.Connection, indexed_only: bool) -> Any:
    """Reading every photo id from the drive takes seconds; it only needs repeating when the library file has changed (its size or time changes
    on every write). None when it cannot be told safely (an in-memory database, or unsaved changes on this connection)."""
    import os

    try:
        if conn.in_transaction:
            return None
        path = conn.execute("PRAGMA database_list").fetchone()[2]
        if not path:
            return None
        stats = []
        for name in (path, path + "-wal"):
            try:
                info = os.stat(name)
                stats.append((info.st_mtime_ns, info.st_size))
            except FileNotFoundError:
                stats.append(None)
        return (path, indexed_only, tuple(stats))
    except Exception:
        return None
