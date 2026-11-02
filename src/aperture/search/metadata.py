"""Path / filename / camera, GPS place and date engines.

Matching is word-prefix based on folded text (``"banga"`` finds the folder
"Bangalore 2019" but ``"art"`` does not find "party"), and all query words
must match, which keeps results precise.
"""

from __future__ import annotations

import sqlite3

import numpy as np

from .textnorm import like_escape, tokens


def _ids(rows: list[tuple[int]] | list[sqlite3.Row]) -> np.ndarray:
    return np.fromiter((r[0] for r in rows), np.int64)


def _word_prefix_ids(conn: sqlite3.Connection, column: str, query: str) -> np.ndarray:
    words = tokens(query, min_len=2)
    if not words:
        return np.zeros(0, np.int64)
    clause = " AND ".join(f"{column} LIKE ? ESCAPE '\\'" for _ in words)
    params = [f"% {like_escape(w)}%" for w in words]  # stored text starts with a space
    return _ids(conn.execute(f"SELECT id FROM items WHERE missing=0 AND {clause} ORDER BY id", params).fetchall())


def path_ids(conn: sqlite3.Connection, query: str) -> np.ndarray:
    """Folders, file names, camera and lens (``items.meta_text``)."""
    return _word_prefix_ids(conn, "meta_text", query)


def place_ids(conn: sqlite3.Connection, query: str) -> np.ndarray:
    """Cities/countries resolved offline from EXIF GPS (``items.place_text``)."""
    return _word_prefix_ids(conn, "place_text", query)


def date_ids(conn: sqlite3.Connection, start: str, end: str) -> np.ndarray:
    """Photos taken in ``[start, end)`` (ISO dates)."""
    return _ids(
        conn.execute("SELECT id FROM items WHERE missing=0 AND taken_at>=? AND taken_at<? ORDER BY id", (start, end)).fetchall()
    )


def all_ids(conn: sqlite3.Connection, *, indexed_only: bool = True) -> np.ndarray:
    """Every live item (the universe for NOT-clauses and 'show everything')."""
    sql = "SELECT id FROM items WHERE missing=0" + (" AND meta_done=1" if indexed_only else "") + " ORDER BY id"
    return _ids(conn.execute(sql).fetchall())
