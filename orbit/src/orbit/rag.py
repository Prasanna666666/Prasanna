"""Search over your own files, so the assistant answers from what your documents actually say and shows where it read it (retrieval-augmented answers).

Orbit uses ONE local model, so retrieval is exact keyword search (SQLite full-text search with BM25 ranking), not a second embedding model: it runs offline, needs no
extra download, and every answer can point at its source. Documents are cut into overlapping passages; notes and finance-file summaries are indexed too. The index is
refreshed incrementally (only changed items are re-read). If full-text search is missing in the SQLite build, a simple word-match search is used instead.
"""

from __future__ import annotations

import hashlib
import re

CHUNK = 700
OVERLAP = 120
WORD = re.compile(r"[\w€₹£.,'-]{3,}", re.UNICODE)
STOP = {"the", "and", "for", "with", "what", "was", "how", "much", "did", "does", "are", "from", "about", "that", "this", "have", "van", "het", "een", "voor", "wat", "hoeveel"}


def _fts(conn) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(source UNINDEXED, ref UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2')")
        conn.execute("CREATE TABLE IF NOT EXISTS search_seen (ref TEXT PRIMARY KEY, digest TEXT NOT NULL)")
        return True
    except Exception:
        return False


def chunks(text: str) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= CHUNK:
        return [text] if text else []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK])
        i += CHUNK - OVERLAP
    return out


def _sources(conn):
    for r in conn.execute("SELECT id, name, text FROM documents"):
        yield f"d{r['id']}", "document", r["name"], r["text"]
    for r in conn.execute("SELECT id, title, body FROM notes"):
        yield f"n{r['id']}", "note", r["title"] or "(note)", r["body"]
    for r in conn.execute("SELECT sha256, name, title, summary, party, reference FROM finance_docs"):
        yield f"f{r['sha256'][:12]}", "file", r["name"], " ".join(x for x in (r["title"], r["summary"], r["party"], r["reference"]) if x)


def reindex(conn) -> int:
    """Bring the index up to date. Returns how many items were (re)indexed."""
    if not _fts(conn):
        return 0
    seen = {r["ref"]: r["digest"] for r in conn.execute("SELECT ref, digest FROM search_seen")}
    done, live = 0, set()
    for ref, source, title, body in _sources(conn):
        live.add(ref)
        digest = hashlib.sha256((title + "\0" + body).encode()).hexdigest()[:16]
        if seen.get(ref) == digest:
            continue
        conn.execute("DELETE FROM search_index WHERE ref=?", (ref,))
        conn.executemany("INSERT INTO search_index (source, ref, title, body) VALUES (?,?,?,?)", [(source, ref, title, c) for c in chunks(body)] or [(source, ref, title, "")])
        conn.execute("INSERT OR REPLACE INTO search_seen (ref, digest) VALUES (?,?)", (ref, digest))
        done += 1
    for gone in set(seen) - live:  # a deleted document or note leaves the index too
        conn.execute("DELETE FROM search_index WHERE ref=?", (gone,))
        conn.execute("DELETE FROM search_seen WHERE ref=?", (gone,))
    conn.commit()
    return done


def terms(question: str) -> list[str]:
    seen, out = set(), []
    for w in WORD.findall(question.lower()):
        w = w.strip(".,'-")
        if len(w) >= 3 and w not in STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:12]


def retrieve(conn, question: str, k: int = 6) -> list[dict]:
    """The best passages for a question, each with where it came from: [{source, title, text, score}]."""
    words = terms(question)
    if not words:
        return []
    if _fts(conn):
        reindex(conn)
        query = " OR ".join('"' + w.replace('"', "") + '"' for w in words)
        try:
            rows = conn.execute("SELECT source, ref, title, snippet(search_index, 3, '[', ']', '…', 40) AS text, bm25(search_index, 0.0, 0.0, 3.0, 1.0) AS score "
                                "FROM search_index WHERE search_index MATCH ? ORDER BY score LIMIT ?", (query, k)).fetchall()
            return [{"source": r["source"], "title": r["title"], "text": r["text"], "score": round(-r["score"], 3)} for r in rows]
        except Exception:
            pass
    out = []  # no full-text search: count the words each item contains
    for ref, source, title, body in _sources(conn):
        hay = (title + " " + body).lower()
        score = sum(hay.count(w) for w in words)
        if score:
            i = max(hay.find(words[0]), 0)
            out.append({"source": source, "title": title, "text": " ".join(body[max(0, i - 80): i + 220].split()), "score": float(score)})
    return sorted(out, key=lambda r: -r["score"])[:k]
