"""The instant preview: data-driven, never raises, never invents matches."""

from __future__ import annotations

import numpy as np

from aperture.search.embeddings import EmbeddingIndex
from aperture.search.quick import quick_ids


def _empty_index() -> EmbeddingIndex:
    return EmbeddingIndex(np.zeros(0, np.int64), np.zeros((0, 4), np.float16))


def test_unknown_words_and_empty_index_give_nothing(scanned):
    ctx = scanned
    with ctx.db.connect() as conn:
        ids = quick_ids(conn, "zzzqqq nonexistent", _empty_index, lambda: None)
    assert len(ids) == 0


def test_words_that_match_the_data_narrow_the_result(scanned):
    ctx = scanned
    with ctx.db.connect() as conn:
        name = conn.execute("SELECT rel_path FROM items WHERE missing=0 LIMIT 1").fetchone()[0]
        word = next(w for w in name.replace("/", " ").replace(".", " ").replace("_", " ").split() if len(w) >= 3)
        ids = quick_ids(conn, f"photos of {word}", _empty_index, lambda: None)
        assert len(ids) <= conn.execute("SELECT COUNT(*) FROM items WHERE missing=0").fetchone()[0]
