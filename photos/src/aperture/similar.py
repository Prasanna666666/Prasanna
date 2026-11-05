"""Groups of similar shots (bursts, retakes, near-identical frames).

Photos are ordered by capture time and each one is compared with its
neighbours; two photos are linked when their CLIP embeddings are close *and*
they were taken within a time window.  Linked photos form a group.  The
neighbour depth bounds the work (linear in library size); it limits how far
apart in the timeline two photos can be compared, never how many groups or
photos are returned.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np

from .search.embeddings import EmbeddingIndex

# preset -> (cosine threshold, window in minutes)
PRESETS: dict[str, tuple[float, float]] = {
    "Nearly identical": (0.96, 10.0),
    "Same scene": (0.92, 30.0),
    "Loosely similar": (0.88, 60.0),
}
NEIGHBOURS = 40


@dataclass(frozen=True)
class SimilarSettings:
    threshold: float = 0.92
    window_minutes: float = 30.0
    neighbours: int = NEIGHBOURS


def _find(parent: np.ndarray, i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def find_similar_groups(conn: sqlite3.Connection, index: EmbeddingIndex, cfg: SimilarSettings | None = None) -> list[list[int]]:
    cfg = cfg or SimilarSettings()
    if len(index) < 2:
        return []
    times = {
        r["id"]: r["taken_at"]
        for r in conn.execute("SELECT id, taken_at FROM items WHERE missing=0 AND kind='image' AND taken_at IS NOT NULL")
    }
    keep = [pos for pos, item_id in enumerate(index.ids.tolist()) if item_id in times]
    if len(keep) < 2:
        return []
    ids = index.ids[keep]
    vectors = index.vectors[keep].astype(np.float32)
    stamps = np.array([times[i].replace(" ", "T")[:19] for i in ids.tolist()], dtype="datetime64[s]").astype(np.int64)
    order = np.argsort(stamps, kind="stable")
    ids, vectors, stamps = ids[order], vectors[order], stamps[order]

    n = len(ids)
    parent = np.arange(n)
    window = cfg.window_minutes * 60.0
    for k in range(1, min(cfg.neighbours, n - 1) + 1):
        sims = np.einsum("ij,ij->i", vectors[:-k], vectors[k:])
        close = (sims >= cfg.threshold) & ((stamps[k:] - stamps[:-k]) <= window)
        for i in np.nonzero(close)[0].tolist():
            a, b = _find(parent, i), _find(parent, i + k)
            if a != b:
                parent[b] = a
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(_find(parent, i), []).append(int(ids[i]))
    return sorted((g for g in groups.values() if len(g) > 1), key=lambda g: (-len(g), g[0]))
