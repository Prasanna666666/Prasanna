"""Looking at a single photo: a vision model describes it, and the description is remembered."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable

from images.config import Paths

from .llm import Describer, LLMError


class NoPreview(LLMError):
    """The photo has no preview image yet, so there is nothing to look at."""


def _preview_bytes(conn: sqlite3.Connection, paths: Paths, item_id: int) -> bytes:
    row = conn.execute("SELECT preview, thumb FROM items WHERE id=? AND missing=0", (item_id,)).fetchone()
    for rel in (row["preview"], row["thumb"]) if row else ():
        if rel and (paths.data / rel).is_file():
            return (paths.data / rel).read_bytes()
    raise NoPreview("This photo has no preview yet, so I cannot look at it. Let indexing finish first.")


def cached_caption(conn: sqlite3.Connection, item_id: int) -> str:
    row = conn.execute("SELECT caption FROM captions WHERE item_id=?", (item_id,)).fetchone()
    return str(row[0]) if row else ""


def describe_item(conn: sqlite3.Connection, paths: Paths, vision: Describer, model: str, item_id: int, question: str = "") -> str:
    """A description of the photo (remembered), or the answer to a specific question about it."""
    if not question.strip():
        known = cached_caption(conn, item_id)
        if known:
            return known
    text = vision.describe(_preview_bytes(conn, paths, item_id), question)
    if text and not question.strip():
        conn.execute(
            "INSERT OR REPLACE INTO captions(item_id, caption, model, created) VALUES (?,?,?,?)",
            (item_id, text, model, time.time()),
        )
        # make the description searchable like any other text found in the photo
        updated = conn.execute("UPDATE fts SET text = text || ' ' || ? WHERE rowid=?", (text, item_id)).rowcount
        if not updated:  # a photo with no other text has no search row yet
            conn.execute("INSERT INTO fts(rowid, text) VALUES (?,?)", (item_id, text))
        conn.commit()
    return text


def caption_all(
    conn: sqlite3.Connection,
    paths: Paths,
    vision: Describer,
    model: str,
    stop: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda done, total: None,
    limit: int = 0,
) -> tuple[int, int]:
    """Describe every photo that has no description yet.  Resumable: finished photos are skipped.

    Returns (described, failed).  Gives up after several failures in a row (model missing or not running)."""
    todo = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM items WHERE missing=0 AND kind='image' AND preview IS NOT NULL "
            "AND id NOT IN (SELECT item_id FROM captions) ORDER BY taken_at DESC, id"
        )
    ]
    if limit:
        todo = todo[:limit]
    described = failed = in_a_row = 0
    for n, item_id in enumerate(todo, 1):
        if stop():
            break
        try:
            describe_item(conn, paths, vision, model, item_id)
            described += 1
            in_a_row = 0
        except LLMError:
            failed += 1
            in_a_row += 1
            if in_a_row >= 5:
                break
        progress(n, len(todo))
    return described, failed
