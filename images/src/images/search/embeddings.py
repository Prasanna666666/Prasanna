"""In-memory CLIP embedding index.

Vectors are stored as float16 (half the RAM: ~170 MB for 170k photos) and are
upcast chunk by chunk during search, so peak extra memory stays small even on
an 8 GB machine.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import numpy as np

CHUNK_ROWS = 16_384


class EmbeddingIndex:
    def __init__(self, ids: np.ndarray, vectors: np.ndarray) -> None:
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must have the same length")
        self.ids = ids.astype(np.int64, copy=False)
        self.vectors = vectors.astype(np.float16, copy=False)

    def __len__(self) -> int:
        return len(self.ids)

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1]) if len(self) else 0

    @classmethod
    def from_db(cls, conn: sqlite3.Connection) -> EmbeddingIndex:
        rows = conn.execute(
            "SELECT e.item_id, e.vec FROM embeddings e JOIN items i ON i.id=e.item_id WHERE i.missing=0 ORDER BY e.item_id"
        ).fetchall()
        if not rows:
            return cls(np.zeros(0, np.int64), np.zeros((0, 0), np.float16))
        ids = np.fromiter((r[0] for r in rows), np.int64, count=len(rows))
        vectors = np.frombuffer(b"".join(r[1] for r in rows), np.float16).reshape(len(rows), -1)
        return cls(ids, vectors)

    def chunks(self, size: int = CHUNK_ROWS) -> Iterator[tuple[int, np.ndarray]]:
        """Yield ``(start_row, float32 block)``."""
        for start in range(0, len(self), size):
            yield start, self.vectors[start : start + size].astype(np.float32)

    def similarity(self, query: np.ndarray) -> np.ndarray:
        """Cosine similarity of ``query`` (L2-normalised) with every photo."""
        out = np.empty(len(self), np.float32)
        q = query.astype(np.float32)
        for start, block in self.chunks():
            out[start : start + len(block)] = block @ q
        return out

    def vector_of(self, item_id: int) -> np.ndarray | None:
        pos = int(np.searchsorted(self.ids, item_id))
        if pos < len(self) and self.ids[pos] == item_id:
            return self.vectors[pos].astype(np.float32)
        return None

    def most_similar(self, item_id: int, k: int = 12) -> tuple[np.ndarray, np.ndarray]:
        """Nearest neighbours of one photo (excluding itself)."""
        vec = self.vector_of(item_id)
        if vec is None or len(self) < 2:
            return np.zeros(0, np.int64), np.zeros(0, np.float32)
        scores = self.similarity(vec)
        scores[self.ids == item_id] = -1.0
        k = min(k, len(self) - 1)
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return self.ids[top], scores[top]
