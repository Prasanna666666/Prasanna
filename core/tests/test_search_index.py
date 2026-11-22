"""The term index (postings) behind document and mail search: the result must be EXACTLY what ranking every passage of every item gives, on random corpora and queries, and the
index must follow every change (edit, delete, purge, an older database) so it can never hide or resurrect content."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from conftest import KEY
from test_documents import build as build_docs
from test_documents import make as make_docs

from atlas_core import documents as documents_module
from atlas_core.access import AllowAll
from atlas_core.documents import RESULT_LIMIT, DocumentIndex, _tokens, terms
from atlas_core.mail import InMemoryMailbox, MailIndex

VOCAB = [f"w{i}" for i in range(12)] + ["the", "is", "total", "due", "invoice", "δοκιμή", "сумма", "राशि"]


def sentence(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(VOCAB) for _ in range(n))


def brute_force_docs(index: DocumentIndex, query: str) -> list[dict]:
    """The old algorithm: every indexed passage of every document, ranked, then verified in order."""
    words = terms(query)
    scored = []
    for row in index._indexed():
        for number, (start, end) in enumerate(json.loads(row["blocks"])):
            passage = index._passage(row, number, start, end)
            hits = sum(1 for w in words if w in set(_tokens(passage["text"])))
            if hits:
                scored.append((-hits, -(row["mtime"] or 0.0), row["rel_path"], number, passage))
    scored.sort(key=lambda s: s[:4])
    out = []
    for *_, passage in scored:
        if index.get(passage["evidence"]["source_id"]) is not None:
            out.append(passage)
        if len(out) >= RESULT_LIMIT:
            break
    return out


def brute_force_mail(index: MailIndex, query: str) -> list[dict]:
    words = terms(query)
    scored = []
    for row in index._conn.execute("SELECT * FROM msgs WHERE status='indexed'").fetchall():
        for ordinal, passage in enumerate(index._passages(row)):
            hits = sum(1 for w in words if w in set(_tokens(passage["text"])))
            if hits:
                scored.append((-hits, -(row["sort_ts"] or 0.0), row["message_id"], ordinal, passage))
    scored.sort(key=lambda s: s[:4])
    out = []
    for *_, passage in scored:
        if index.get(passage["evidence"]["source_id"]) is not None:
            out.append(passage)
        if len(out) >= RESULT_LIMIT:
            break
    return out


def queries(rng: random.Random, count: int) -> list[str]:
    return [" ".join(rng.choice(VOCAB) for _ in range(rng.randint(1, 6))) for _ in range(count)]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_document_search_equals_ranking_every_passage(tmp_path, seed):
    rng = random.Random(seed)
    files = {f"d{i:03d}.txt": "\n\n".join(sentence(rng, rng.randint(3, 12)) for _ in range(rng.randint(1, 5))) for i in range(60)}
    index = make_docs(
        tmp_path, files, times={name: 1_700_000_000 + rng.randint(0, 50) * 86_400 for name in files}
    )  # many equal mtimes: ties must resolve the same way
    build_docs(index)
    for q in queries(rng, 120):
        assert index.search("documents", q) == brute_force_docs(index, q), q


@pytest.mark.parametrize("seed", [4, 5])
def test_mail_search_equals_ranking_every_passage(tmp_path, seed):
    rng = random.Random(seed)
    messages = [
        {
            "message_id": f"m{i:04d}@example.invalid",
            "sender": f"p{i % 7}@example.invalid",
            "date": f"2026-{1 + i % 12:02d}-{1 + i % 27:02d}T09:00:00+00:00",
            "subject": sentence(rng, 3),
            "body": "\n\n".join(sentence(rng, rng.randint(3, 10)) for _ in range(rng.randint(1, 4))),
        }
        for i in range(60)
    ]
    index = MailIndex(tmp_path / "m.db", KEY, InMemoryMailbox(messages), "mail", access=AllowAll())
    index.scan()
    while index.run(10)["pending"]:
        pass
    for q in queries(rng, 100):
        assert index.search("mail", q) == brute_force_mail(index, q), q


def test_a_common_word_does_not_make_search_read_every_document(tmp_path):
    files = {f"d{i:03d}.txt": ("alpha beta the" if i % 7 == 0 else "the plain text") + f" number{i}" for i in range(210)}
    index = make_docs(tmp_path, files)
    build_docs(index)
    fetched: list[int] = []
    real = index._fetch
    index._fetch = lambda keys: (fetched.append(len(keys)), real(keys))[1]  # type: ignore[method-assign]
    found = index.search("documents", "alpha beta the")
    assert len(found) == RESULT_LIMIT and all("alpha" in p["text"] for p in found)
    assert fetched == [30]  # only the thirty documents holding all three words were read; the 180 that hold just "the" never were
    assert found == brute_force_docs(index, "alpha beta the")


def test_the_index_follows_edits_deletes_and_purge(tmp_path):
    index = make_docs(tmp_path, {"a.txt": "alpha unique1", "b.txt": "beta unique2"})
    build_docs(index)
    posted = lambda: sorted(tuple(r) for r in index._conn.execute("SELECT term, key FROM postings"))  # noqa: E731
    assert ("unique1", "a.txt") in posted()
    path = tmp_path / "docs" / "a.txt"
    path.write_text("gamma unique3")
    import os

    os.utime(path, (1_800_000_000, 1_800_000_000))
    index.scan()
    assert not [p for p in posted() if p[1] == "a.txt"] and index.search("documents", "unique1") == []  # pending: no old words, no old text
    while index.run(5)["pending"]:
        pass
    assert ("unique3", "a.txt") in posted() and ("unique1", "a.txt") not in posted()
    path.unlink()
    index.scan()
    assert not [p for p in posted() if p[1] == "a.txt"]
    index.purge()
    assert posted() == [] and index.search("documents", "beta") == []


def test_an_index_written_before_the_term_table_existed_is_upgraded_in_place(tmp_path):
    index = make_docs(tmp_path, {"a.txt": "alpha unique1", "b.txt": "beta unique2"})
    build_docs(index)
    before = index.search("documents", "unique1")
    index._conn.execute("DROP TABLE postings")
    index._conn.execute("PRAGMA user_version = 1")
    index.close()
    reopened = DocumentIndex(tmp_path / "index.db", KEY, tmp_path / "docs", "documents", access=AllowAll())
    assert reopened.search("documents", "unique1") == before and before
    assert reopened._conn.execute("PRAGMA user_version").fetchone()[0] == documents_module.SCHEMA_VERSION


def test_a_newer_index_than_this_code_is_still_refused(tmp_path):
    index = make_docs(tmp_path, {"a.txt": "alpha"})
    index._conn.execute("PRAGMA user_version = 99")
    index.close()
    with pytest.raises(ValueError, match="newer"):
        DocumentIndex(tmp_path / "index.db", KEY, tmp_path / "docs", "documents", access=AllowAll())


def test_nothing_in_the_term_table_is_readable_without_the_key(tmp_path):
    index = make_docs(tmp_path, {"a.txt": "alpha secretword9"})
    build_docs(index)
    index.close()
    assert b"secretword9" not in Path(tmp_path / "index.db").read_bytes()
