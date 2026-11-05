"""Finance's search over its own files, notes and described documents: the shared retrieval (kit.rag) with Finance's sources."""

from __future__ import annotations

from kit.rag import chunks, terms
from kit.rag import reindex as _reindex
from kit.rag import retrieve as _retrieve

__all__ = ["chunks", "reindex", "retrieve", "terms"]


def _sources(conn):
    for r in conn.execute("SELECT id, name, text FROM documents"):
        yield f"d{r['id']}", "document", r["name"], r["text"]
    for r in conn.execute("SELECT id, title, body FROM notes"):
        yield f"n{r['id']}", "note", r["title"] or "(note)", r["body"]
    for r in conn.execute("SELECT sha256, name, title, summary, party, reference FROM finance_docs"):
        yield f"f{r['sha256'][:12]}", "file", r["name"], " ".join(x for x in (r["title"], r["summary"], r["party"], r["reference"]) if x)


def reindex(conn) -> int:
    return _reindex(conn, _sources)


def retrieve(conn, question: str, k: int = 6, alternatives: list[str] | None = None) -> list[dict]:
    return _retrieve(conn, question, k, alternatives, sources=_sources)
