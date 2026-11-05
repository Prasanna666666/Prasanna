"""Full-text search over OCR text and document text (FTS5).

Matching is *substring based* (trigram tokenizer) so partial words and numbers
work ("18.40", "4417", "recei" -> "receipt").  Every matching photo is
returned: there is deliberately no LIMIT anywhere in this module.
"""

from __future__ import annotations

import re
import sqlite3

import numpy as np

from ..db import meta_get
from .textnorm import like_escape

_TERM = re.compile(r'"([^"]+)"|(\S+)')
SNIPPET_WIDTH = 90


def parse_terms(query: str) -> list[str]:
    """Split on whitespace but keep ``"quoted phrases"`` together."""
    return [(a or b).strip() for a, b in _TERM.findall(query) if (a or b).strip()]


def _fts_quote(term: str, tokenizer: str) -> str:
    quoted = '"' + term.replace('"', '""') + '"'
    return quoted if tokenizer == "trigram" else quoted + "*"


def search_text_ids(conn: sqlite3.Connection, query: str, *, phrase: bool = False) -> np.ndarray:
    """Ids of every photo whose text contains ALL terms (best match first)."""
    terms = [query.strip().strip('"')] if phrase else parse_terms(query)
    terms = [t for t in terms if t]
    if not terms:
        return np.zeros(0, np.int64)
    tokenizer = meta_get(conn, "fts_tokenizer", "trigram") or "trigram"
    long_terms = [t for t in terms if len(t) >= 3] if tokenizer == "trigram" else terms
    short_terms = [t for t in terms if t not in long_terms]  # trigram cannot index < 3 chars
    where, params = ["i.missing=0"], []
    if long_terms:
        where.append("fts MATCH ?")
        params.append(" AND ".join(_fts_quote(t, tokenizer) for t in long_terms))
    for term in short_terms:
        where.append("fts.text LIKE ? ESCAPE '\\'")
        params.append(f"%{like_escape(term)}%")
    order = "ORDER BY bm25(fts)" if long_terms else "ORDER BY fts.rowid"
    sql = f"SELECT fts.rowid FROM fts JOIN items i ON i.id=fts.rowid WHERE {' AND '.join(where)} {order}"
    return np.fromiter((r[0] for r in conn.execute(sql, params)), np.int64)


def make_snippet(text: str, terms: list[str], width: int = SNIPPET_WIDTH) -> str:
    """Excerpt around the first hit with matches wrapped in ``\\x02 ... \\x03``."""
    flat = re.sub(r"\s+", " ", text)
    lowered = flat.lower()
    hits = [lowered.find(t.lower()) for t in terms if t and t.lower() in lowered]
    start = max(0, (min(hits) if hits else 0) - width)
    stop = start + 2 * width + 40
    fragment = flat[start:stop]
    for term in sorted(set(terms), key=len, reverse=True):
        if term:
            fragment = re.sub(re.escape(term), lambda m: f"\x02{m.group(0)}\x03", fragment, flags=re.IGNORECASE)
    return ("... " if start else "") + fragment + (" ..." if stop < len(flat) else "")
