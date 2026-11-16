"""Documents that read alike are asked about once. What the model said about a document that is about none of the apps is remembered with a fingerprint of its words; a new document
whose words are almost the same as one remembered is given the same answer, without asking the model again. Nothing here knows what any document is: the answers are the model's own,
and the fingerprint only says "this reads like that one"."""

from __future__ import annotations

import re
import zlib

HASHES = 32  # the fingerprint: the smallest of this many differently mixed hashes of the document's three-word groups
BAND = 4  # hashes per band: two documents become candidates when a whole band is equal
SAME = 0.85  # share of equal hashes from which two documents are taken to read alike (about the same share of their three-word groups)
MIN_GROUPS = 8  # a document with fewer three-word groups says too little to be compared
LOOK_AT = 4000  # characters from the start of the document


def signature(text: str) -> list[int] | None:
    words = re.findall(r"\w+", text[:LOOK_AT].lower())
    groups = {" ".join(words[i : i + 3]) for i in range(len(words) - 2)}
    if len(groups) < MIN_GROUPS:
        return None
    return [min(zlib.crc32(f"{k}|{g}".encode()) for g in groups) for k in range(HASHES)]


def bands(sig: list[int]) -> list[tuple[int, int]]:
    return [(b, zlib.crc32(",".join(map(str, sig[b * BAND : (b + 1) * BAND])).encode())) for b in range(HASHES // BAND)]


def similarity(a: list[int], b: list[int]) -> float:
    return sum(x == y for x, y in zip(a, b, strict=True)) / HASHES


def remember(conn, doc_id: int, sig: list[int]) -> None:
    conn.execute("UPDATE documents SET sig=? WHERE id=?", (",".join(map(str, sig)), doc_id))
    conn.executemany("INSERT INTO sigs (doc_id, band, h) VALUES (?,?,?)", [(doc_id, b, h) for b, h in bands(sig)])


def nearest(conn, sig: list[int]) -> tuple[int, float] | None:
    """The remembered document that reads most like this one, if any reads alike enough: (its id, how much)."""
    ids: set[int] = set()
    for b, h in bands(sig):
        ids.update(r[0] for r in conn.execute("SELECT doc_id FROM sigs WHERE band=? AND h=?", (b, h)))
    best: tuple[int, float] | None = None
    for doc_id in ids:
        row = conn.execute("SELECT sig FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not row or not row[0]:
            continue
        score = similarity(sig, [int(x) for x in row[0].split(",")])
        if score >= SAME and (best is None or score > best[1]):
            best = (doc_id, score)
    return best
