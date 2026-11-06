"""Search over your own files, so the assistant answers from what your documents actually say and shows where it read it (retrieval-augmented answers).

Finance uses ONE local model, so retrieval is exact keyword search (SQLite full-text search with BM25 ranking), not a second embedding model: it runs offline, needs no
extra download, and every answer can point at its source. Documents are cut into overlapping passages; notes and finance-file summaries are indexed too. The index is
refreshed incrementally (only changed items are re-read). If full-text search is missing in the SQLite build, a simple word-match search is used instead.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3

from . import log

CHUNK = 700
OVERLAP = 120
WORD = re.compile(r"[\w€₹£.,'-]{3,}", re.UNICODE)
STOP = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "was",
    "how",
    "much",
    "did",
    "does",
    "are",
    "from",
    "about",
    "that",
    "this",
    "have",
    "van",
    "het",
    "een",
    "voor",
    "wat",
    "hoeveel",
    # words of asking, not of the thing asked about ("show me my Ziggo invoices" is about Ziggo)
    "show",
    "give",
    "send",
    "get",
    "find",
    "list",
    "open",
    "display",
    "please",
    "all",
    "any",
    "documents",
    "document",
    "files",
    "file",
    "pdfs",
    "can",
    "could",
    "would",
    "want",
    "need",
    "see",
    "some",
    "them",
    "those",
    "these",
    "there",
    "here",
    "you",
    "your",
    "our",
}


def _fts(conn) -> bool:
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(source UNINDEXED, ref UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2')"
        )
        conn.execute("CREATE TABLE IF NOT EXISTS search_seen (ref TEXT PRIMARY KEY, digest TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS search_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        have = {r[1] for r in conn.execute("PRAGMA table_info(search_seen)")}
        for column in (
            "first_row",
            "last_row",
        ):  # where an item's passages sit in the index: deleting by row number is instant, deleting by ref scans everything
            if column not in have:
                conn.execute(f"ALTER TABLE search_seen ADD COLUMN {column} INTEGER")
        return True
    except sqlite3.Error as exc:  # no FTS5 in this SQLite build: search falls back to counting words
        log.failed("fts5 unavailable", exc)
        return False


def chunks(text: str) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= CHUNK:
        return [text] if text else []
    out, i = [], 0
    while i < len(text):
        out.append(text[i : i + CHUNK])
        i += CHUNK - OVERLAP
    return out


def _forget(conn, ref: str, first: int | None, last: int | None) -> None:
    """Take an item's passages out of the index (by row number when known; the slow way only for items indexed by an older version)."""
    if first is not None and last is not None:
        conn.execute("DELETE FROM search_index WHERE rowid BETWEEN ? AND ?", (first, last))
    else:
        conn.execute("DELETE FROM search_index WHERE ref=?", (ref,))


def reindex(conn, sources, fingerprint: str = "") -> int:
    """Bring the index up to date. Returns how many items were (re)indexed. With a `fingerprint` that has not changed since the last time, nothing is read at all."""
    if not _fts(conn):
        return 0
    if fingerprint:
        row = conn.execute("SELECT value FROM search_state WHERE key='fingerprint'").fetchone()
        if row and row[0] == fingerprint:
            return 0
    seen = {r["ref"]: (r["digest"], r["first_row"], r["last_row"]) for r in conn.execute("SELECT ref, digest, first_row, last_row FROM search_seen")}
    done, live = 0, set()
    for ref, source, title, body in sources(conn):
        live.add(ref)
        digest = hashlib.sha256((title + "\0" + body).encode()).hexdigest()[:16]
        before = seen.get(ref)
        if before and before[0] == digest:
            continue
        if before:  # changed: its old passages go; a new item has none, so nothing is searched for
            _forget(conn, ref, before[1], before[2])
        rows = [(source, ref, title, c) for c in chunks(body)] or [(source, ref, title, "")]
        first = last = None
        for row in rows:
            last = conn.execute("INSERT INTO search_index (source, ref, title, body) VALUES (?,?,?,?)", row).lastrowid
            first = first if first is not None else last
        conn.execute("INSERT OR REPLACE INTO search_seen (ref, digest, first_row, last_row) VALUES (?,?,?,?)", (ref, digest, first, last))
        done += 1
    for gone, (_digest, first, last) in seen.items():  # a deleted document or note leaves the index too
        if gone not in live:
            _forget(conn, gone, first, last)
            conn.execute("DELETE FROM search_seen WHERE ref=?", (gone,))
    if fingerprint:
        conn.execute("INSERT OR REPLACE INTO search_state (key, value) VALUES ('fingerprint', ?)", (fingerprint,))
    conn.commit()
    return done


def terms(question: str) -> list[str]:
    seen, out = set(), []
    for raw in WORD.findall(question.lower()):
        w = raw.strip(".,'-")
        if len(w) >= 3 and w not in STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:12]


RRF_K = 60  # reciprocal-rank fusion: how quickly a lower rank stops counting


def _stem(word: str) -> str:
    """A rough stem for English and Dutch endings, so "invoices" and "invoiced" both look for "invoic"."""
    for ending in ("ing", "ed", "es", "en", "s", "e"):
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: -len(ending)]
    return word


def _match_query(words: list[str]) -> str:
    """Every word, matching any ending of its stem (longer words only, so short words stay exact)."""
    parts = []
    for raw in words:
        w = raw.replace('"', "")
        stem = _stem(w)
        parts.append(f'"{stem}"*' if len(stem) >= 4 else f'"{w}"')
    return " OR ".join(parts)


def _ranked(conn, words: list[str], k: int) -> list[dict] | None:
    """Passages for one phrasing, best first. None when full-text search could not run the query."""
    try:
        rows = conn.execute(
            "SELECT source, ref, rowid AS rid, title, snippet(search_index, 3, '[', ']', '…', 40) AS text, bm25(search_index, 0.0, 0.0, 3.0, 1.0) AS score "
            "FROM search_index WHERE search_index MATCH ? ORDER BY score LIMIT ?",
            (_match_query(words), k * 3),
        ).fetchall()
    except sqlite3.Error as exc:  # a query FTS5 cannot parse: fall back to word counting
        log.failed("fts5 query failed", exc)
        return None
    return [{"rid": r["rid"], "source": r["source"], "title": r["title"], "text": r["text"], "score": round(-r["score"], 3)} for r in rows]


def retrieve(conn, question: str, k: int = 6, alternatives: list[str] | None = None, *, sources, fingerprint: str = "") -> list[dict]:
    """The best passages for a question, each with where it came from: [{source, title, text, score}].

    The assistant may pass other ways of asking the same thing (synonyms, the other language: "dekking" for "cover"). Each phrasing is searched and the
    results are fused by rank, so a passage that several phrasings agree on comes first."""
    phrasings = [question, *[a for a in (alternatives or []) if isinstance(a, str)]][:5]
    searches = [w for w in (terms(p) for p in phrasings) if w]
    if not searches:
        return []
    if _fts(conn):
        reindex(conn, sources, fingerprint)
        fused: dict[int, dict] = {}
        for words in searches:
            ranked = _ranked(conn, words, k)
            if ranked is None:
                break
            for rank, hit in enumerate(ranked):
                got = fused.setdefault(hit["rid"], {**hit, "score": 0.0})
                got["score"] += 1.0 / (RRF_K + rank)
        else:
            best = sorted(fused.values(), key=lambda h: -h["score"])[:k]
            return [{"source": h["source"], "title": h["title"], "text": h["text"], "score": round(h["score"] * RRF_K, 3)} for h in best]
    words = [w for group in searches for w in group]
    out = []  # no full-text search: count the words each item contains
    for _ref, source, title, body in sources(conn):
        hay = (title + " " + body).lower()
        score = sum(hay.count(w) for w in words)
        if score:
            i = max(hay.find(words[0]), 0)
            out.append({"source": source, "title": title, "text": " ".join(body[max(0, i - 80) : i + 220].split()), "score": float(score)})
    return sorted(out, key=lambda r: -r["score"])[:k]
