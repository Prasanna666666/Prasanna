"""Looking at a single photo: a vision model describes it, and the description is remembered."""

from __future__ import annotations

import sqlite3
import time

from ..config import Paths
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
        conn.commit()
    return text
