"""Read-only library queries used by the UI (no limits, typed results)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from .db import chunked, in_clause
from .models import Item
from .search.textnorm import like_escape


def items_by_ids(conn: sqlite3.Connection, ids: Iterable[int]) -> dict[int, Item]:
    """Fetch many items at once; unknown ids are simply absent from the result."""
    wanted = [int(i) for i in ids]
    out: dict[int, Item] = {}
    for part in chunked(wanted):
        for row in conn.execute(f"SELECT * FROM items WHERE id IN ({in_clause(part)})", part):
            out[row["id"]] = Item.from_row(row)
    return out


def get_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    row = conn.execute("SELECT * FROM items WHERE id=?", (int(item_id),)).fetchone()
    return Item.from_row(row) if row else None


def item_ids(
    conn: sqlite3.Connection,
    kinds: tuple[str, ...] = ("image", "pdf", "text"),
    year: int | None = None,
    name_like: str = "",
    newest_first: bool = True,
    hide_defects: bool = False,
) -> np.ndarray:
    """Ids of every matching item, sorted by capture date.  No LIMIT."""
    if not kinds:
        return np.zeros(0, np.int64)
    where, params = ["missing=0", "meta_done=1", f"kind IN ({in_clause(list(kinds))})"], list(kinds)
    if year:
        where.append("substr(taken_at,1,4)=?")
        params.append(str(year))
    if name_like.strip():
        where.append("rel_path LIKE ? ESCAPE '\\'")
        params.append(f"%{like_escape(name_like.strip())}%")
    if hide_defects:
        where.append("id NOT IN (SELECT item_id FROM flags WHERE status='defect')")
    order = "DESC" if newest_first else "ASC"
    rows = conn.execute(f"SELECT id FROM items WHERE {' AND '.join(where)} ORDER BY taken_at {order}, id", params)
    return np.fromiter((r[0] for r in rows), np.int64)


def years_available(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT CAST(substr(taken_at,1,4) AS INTEGER) AS y FROM items "
        "WHERE missing=0 AND taken_at IS NOT NULL ORDER BY y DESC"
    )
    return [r["y"] for r in rows if r["y"]]


def item_text(conn: sqlite3.Connection, item_id: int, limit: int = 4000) -> str:
    row = conn.execute("SELECT substr(text, 1, ?) FROM fts WHERE rowid=?", (limit, item_id)).fetchone()
    return row[0] if row else ""


@dataclass(frozen=True)
class Coverage:
    total: int
    indexed: int
    embedded: int
    faces_done: int
    ocr_done: int
    failed: int

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.indexed == self.total


def coverage(conn: sqlite3.Connection) -> Coverage:
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(meta_done),0), COALESCE(SUM(clip_done),0), COALESCE(SUM(faces_done),0), "
        "COALESCE(SUM(ocr_done),0), COALESCE(SUM(error IS NOT NULL),0) FROM items WHERE missing=0"
    ).fetchone()
    return Coverage(*(int(v) for v in row))
