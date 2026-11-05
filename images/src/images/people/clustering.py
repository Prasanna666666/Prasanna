"""Group face embeddings into people.

Incremental by design: faces already assigned stay put, new faces join the
closest existing person (cosine >= threshold) or form new groups.  Named
people and manual corrections (``locked`` faces) always survive a regroup.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

import numpy as np

from ..db import meta_set


@dataclass(frozen=True)
class ClusterResult:
    assigned: int = 0
    new_people: int = 0


def _normalize_rows(a: np.ndarray) -> np.ndarray:
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)


def _best_match(embeddings: np.ndarray, centroids: np.ndarray, chunk: int = 4096) -> tuple[np.ndarray, np.ndarray]:
    """Per row: index of the most similar centroid and that similarity."""
    index = np.empty(len(embeddings), np.int64)
    sim = np.empty(len(embeddings), np.float32)
    for start in range(0, len(embeddings), chunk):
        m = embeddings[start : start + chunk] @ centroids.T
        index[start : start + chunk] = m.argmax(1)
        sim[start : start + chunk] = m.max(1)
    return index, sim


def greedy_cluster(embeddings: np.ndarray, threshold: float, refine: int = 2) -> np.ndarray:
    """Quality-ordered leader clustering + refinement + merge of duplicates.

    ``embeddings`` must be L2-normalised and sorted best-quality first."""
    n, dim = embeddings.shape
    labels = np.full(n, -1, np.int64)
    capacity = 256
    sums = np.zeros((capacity, dim), np.float32)
    cents = np.zeros((capacity, dim), np.float32)
    k = 0
    for i in range(n):
        if k:
            sims = cents[:k] @ embeddings[i]
            j = int(sims.argmax())
            if sims[j] >= threshold:
                labels[i] = j
                sums[j] += embeddings[i]
                cents[j] = sums[j] / max(float(np.linalg.norm(sums[j])), 1e-9)
                continue
        if k == capacity:
            capacity *= 2
            sums = np.vstack([sums, np.zeros_like(sums)])
            cents = np.vstack([cents, np.zeros_like(cents)])
        sums[k] = cents[k] = embeddings[i]
        labels[i] = k
        k += 1
    for _ in range(refine):  # re-assign every face against the settled centroids
        centroids = np.zeros((k, dim), np.float32)
        np.add.at(centroids, labels, embeddings)
        best, sim = _best_match(embeddings, _normalize_rows(centroids))
        labels = np.where(sim >= threshold, best, labels)
    centroids = np.zeros((k, dim), np.float32)
    np.add.at(centroids, labels, embeddings)
    centroids = _normalize_rows(centroids)
    if 1 < k <= 8000:  # merge clusters that are really the same person
        parent = list(range(k))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        similarity = centroids @ centroids.T
        for a, b in zip(*np.where(np.triu(similarity >= threshold + 0.05, 1)), strict=True):
            parent[find(int(a))] = find(int(b))
        labels = np.array([find(int(x)) for x in labels])
    _, labels = np.unique(labels, return_inverse=True)
    return labels


def cluster_faces(
    conn: sqlite3.Connection,
    *,
    threshold: float = 0.40,
    rebuild: bool = False,
    min_score: float = 0.6,
    min_px: int = 40,
) -> ClusterResult:
    """Assign ungrouped faces to people.  ``rebuild`` first dissolves *unnamed*
    automatic groups (named people and manual corrections are preserved)."""
    if rebuild:
        conn.execute("UPDATE faces SET person_id=NULL WHERE locked=0 AND person_id IN (SELECT id FROM people WHERE name IS NULL)")
        conn.execute(
            "DELETE FROM people WHERE name IS NULL AND id NOT IN "
            "(SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)"
        )
    pending = conn.execute(
        "SELECT id, emb FROM faces WHERE person_id IS NULL AND locked=0 AND score>=? AND px>=? ORDER BY score DESC",
        (min_score, min_px),
    ).fetchall()
    if not pending:
        conn.commit()
        return ClusterResult()
    ids = np.array([r["id"] for r in pending])
    embs = np.vstack([np.frombuffer(r["emb"], np.float32) for r in pending])

    assigned = 0
    remaining = np.ones(len(ids), bool)
    known = conn.execute("SELECT person_id, emb FROM faces WHERE person_id IS NOT NULL").fetchall()
    if known:  # 1) join existing people
        person_ids = np.array([r["person_id"] for r in known])
        matrix = np.vstack([np.frombuffer(r["emb"], np.float32) for r in known])
        unique, inverse = np.unique(person_ids, return_inverse=True)
        centroids = np.zeros((len(unique), matrix.shape[1]), np.float32)
        np.add.at(centroids, inverse, matrix)
        best, sim = _best_match(embs, _normalize_rows(centroids))
        ok = sim >= threshold
        conn.executemany(
            "UPDATE faces SET person_id=? WHERE id=?",
            [(int(unique[b]), int(i)) for b, i in zip(best[ok], ids[ok], strict=True)],
        )
        assigned += int(ok.sum())
        remaining = ~ok

    new_people = 0
    if remaining.any():  # 2) group the rest into new people
        labels = greedy_cluster(embs[remaining], threshold)
        now = time.time()
        created = {
            int(label): conn.execute("INSERT INTO people(created_at) VALUES (?)", (now,)).lastrowid for label in np.unique(labels)
        }
        conn.executemany(
            "UPDATE faces SET person_id=? WHERE id=?",
            [(created[int(lab)], int(i)) for lab, i in zip(labels, ids[remaining], strict=True)],
        )
        assigned += int(remaining.sum())
        new_people = len(created)
    meta_set(conn, "people_version", str(time.time()))
    conn.commit()
    return ClusterResult(assigned=assigned, new_people=new_people)
