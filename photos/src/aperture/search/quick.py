"""Instant first answer: a direct lookup that runs in milliseconds while the AI plans.

It is only a preview.  The agent's checked answer replaces it a moment later.  Nothing
here is a fixed rule about meaning: each word of the request is tried against the
library's own data (places, folders, file names, text found in photos), and words that
match nothing, or match almost everything, simply do not narrow the result.  When no
word matches the data, the request is compared with the photos by what they show."""

from __future__ import annotations

import itertools
import sqlite3
from collections.abc import Callable

import numpy as np

from ..ml.protocols import ImageEmbedder
from .embeddings import EmbeddingIndex
from .metadata import path_ids, place_ids, remembered
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
    total = remembered(conn, "live_count", lambda: conn.execute("SELECT COUNT(*) FROM items WHERE missing=0").fetchone()[0]) or 1
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


FILLER = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "these",
        "those",
        "was",
        "were",
        "are",
        "you",
        "your",
        "yours",
        "show",
        "give",
        "get",
        "find",
        "see",
        "take",
        "took",
        "taken",
        "pic",
        "pics",
        "picture",
        "pictures",
        "photo",
        "photos",
        "image",
        "images",
        "all",
        "any",
        "some",
        "please",
        "can",
        "could",
        "would",
        "should",
        "who",
        "what",
        "when",
        "where",
        "which",
        "how",
        "many",
        "much",
        "more",
        "most",
        "last",
        "next",
        "ago",
        "back",
        "year",
        "years",
        "month",
        "months",
        "week",
        "weeks",
        "day",
        "days",
        "today",
        "yesterday",
        "them",
        "they",
        "their",
        "there",
        "then",
        "than",
        "have",
        "has",
        "had",
        "into",
        "onto",
        "over",
        "under",
        "about",
        "around",
        "only",
        "just",
        "also",
        "not",
        "without",
        "his",
        "her",
        "him",
        "its",
        "our",
        "out",
        "off",
        "one",
        "two",
        "let",
        "lets",
        "want",
        "need",
        "like",
        "me",
        "mine",
    ]
)


def probe(conn: sqlite3.Connection, request: str, people: Callable[[str], int] | None = None) -> str:
    """Facts about how the request's words relate to THIS library, for the planner.

    Each word and each pair of neighbouring words is tried against places, folders and file
    names, text found in photos, and (when given) people.  Only hits are reported, with their
    counts, so the model picks the engine that really holds the word instead of guessing."""
    words = [w for w in tokens(request, min_len=2) if w not in FILLER]  # filler words match everything and cost a lookup each
    phrases = list(dict.fromkeys([w for w in words if len(w) >= 3] + [f"{a} {b}" for a, b in itertools.pairwise(words)]))
    total = remembered(conn, "live_count", lambda: conn.execute("SELECT COUNT(*) FROM items WHERE missing=0").fetchone()[0]) or 1
    lines: list[str] = []
    for phrase in phrases[:8]:
        hits = {
            "place": len(place_ids(conn, phrase)),
            "folder/file name": len(path_ids(conn, phrase)),
            "text in photos": len(search_text_ids(conn, phrase)),
        }
        if people is not None:
            hits["person"] = people(phrase)
        found = {k: n for k, n in hits.items() if 0 < n <= total * TOO_COMMON}
        if found:
            lines.append(f"'{phrase}' -> " + ", ".join(f"{k}: {n:,} photos" for k, n in found.items()))
    if not lines:
        return ""
    return "DATA MATCHES FOR WORDS IN THE REQUEST (a word with no match is not stored as place/name/text):\n" + "\n".join(lines)
