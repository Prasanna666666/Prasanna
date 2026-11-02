"""Instant first answer: a direct lookup that runs in milliseconds while the AI plans.

It is only a preview.  The agent's checked answer replaces it a moment later.  Nothing
here is a fixed rule about meaning: each word of the request is tried against the
library's own data (places, folders, file names, text found in photos), and words that
match nothing, or match almost everything, simply do not narrow the result.  When no
word matches the data, the request is compared with the photos by what they show."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

import numpy as np

from ..ml.protocols import ImageEmbedder
from .embeddings import EmbeddingIndex
from .metadata import path_ids, place_ids
from .text import search_text_ids
from .textnorm import tokens
from .visual import VisualSearch

TOO_COMMON = 0.5  # a word found in more than half of the library says nothing about this request


def _word_ids(conn: sqlite3.Connection, word: str) -> np.ndarray:
    return np.unique(np.concatenate([place_ids(conn, word), path_ids(conn, word), search_text_ids(conn, word)]))


def quick_ids(
    conn: sqlite3.Connection,
    request: str,
    index: Callable[[], EmbeddingIndex],
    embedder: Callable[[], ImageEmbedder | None],
    strictness: str = "balanced",
) -> np.ndarray:
    """Ids likely to match ``request``, best guess first; empty when nothing fits."""
    total = conn.execute("SELECT COUNT(*) FROM items WHERE missing=0").fetchone()[0] or 1
    narrowed: np.ndarray | None = None
    for word in dict.fromkeys(tokens(request, min_len=3)):
        ids = _word_ids(conn, word)
        if len(ids) == 0 or len(ids) / total > TOO_COMMON:
            continue
        narrowed = ids if narrowed is None else np.intersect1d(narrowed, ids)
    if narrowed is not None:
        return narrowed
    model = embedder()
    idx = index()
    if model is None or len(idx) == 0:
        return np.zeros(0, np.int64)
    return VisualSearch(idx, model, strictness).search(request).ids
