"""What is IN each picture, read once and stored: labels, objects with boxes, text with boxes, landmark and scene tags.

Reads the small stored preview of each photo (the original is never opened here) and writes plain rows, so every later question
is a database lookup. Resumable; commits as it goes.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np

from ..config import preview_rel
from ..ml.vision_details import Details

VERSION = 1
CLIP_TOP = 8
CLIP_MIN_SCORE = 0.22  # cosine between image and "a photo of <label>" below which a tag is noise


def vocabulary() -> list[str]:
    text = resources.files("aperture.data").joinpath("tag_vocabulary.txt").read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def pending(conn: sqlite3.Connection, limit: int = 0) -> list[int]:
    sql = ("SELECT i.id FROM items i LEFT JOIN photo_details d ON d.item_id=i.id "
           "WHERE i.missing=0 AND i.meta_done=1 AND i.kind='image' AND (d.item_id IS NULL OR d.version < ?) ORDER BY i.id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r[0] for r in conn.execute(sql, (VERSION,))]


def store(conn: sqlite3.Connection, item_id: int, details: Details) -> None:
    for table in ("photo_labels", "photo_objects", "photo_text"):
        conn.execute(f"DELETE FROM {table} WHERE item_id=? " + ("AND source='vision'" if table == "photo_labels" else ""), (item_id,))
    conn.executemany("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,?,'vision')",
                     [(item_id, label.lower(), score) for label, score in details.labels])
    conn.executemany("INSERT INTO photo_objects(item_id, kind, label, score, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?,?)",
                     [(item_id, kind, label, score, *box) for kind, label, score, box in details.objects])
    conn.executemany("INSERT INTO photo_text(item_id, text, score, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?)",
                     [(item_id, text, score, *box) for text, score, box in details.texts])
    conn.execute("INSERT OR REPLACE INTO photo_details(item_id, version, read_at) VALUES (?,?,?)", (item_id, VERSION, time.time()))


def run(conn: sqlite3.Connection, data_dir: Path, analyser: Any, limit: int = 0, stop: Any = None,
        report: Callable[[int, int], None] | None = None) -> tuple[int, int]:
    """Analyse every picture that has no record yet. Returns (done, unreadable)."""
    todo = pending(conn, limit)
    done = bad = 0
    for n, item_id in enumerate(todo, 1):
        if stop is not None and stop.is_set():
            break
        path = data_dir / preview_rel(item_id)
        try:
            store(conn, item_id, analyser.analyse(path.read_bytes()))
            done += 1
        except Exception as exc:  # one unreadable preview must not stop the pass; it is recorded and skipped
            conn.execute("INSERT OR REPLACE INTO photo_details(item_id, version, read_at, notes) VALUES (?,?,?,?)",
                         (item_id, VERSION, time.time(), f"{type(exc).__name__}: {exc}"[:300]))
            bad += 1
        if n % 100 == 0:
            conn.commit()
            if report:
                report(n, len(todo))
    conn.commit()
    return done, bad


def clip_tags(conn: sqlite3.Connection, index: Any, embedder: Any, labels: list[str] | None = None, top: int = CLIP_TOP,
              min_score: float = CLIP_MIN_SCORE) -> int:
    """Tag every photo with the vocabulary labels its stored embedding is closest to (no image is decoded: seconds, not hours)."""
    labels = labels or vocabulary()
    if len(index) == 0 or not labels:
        return 0
    text = embedder.embed_text([f"a photo of {label}" for label in labels]).astype(np.float32)
    text /= np.maximum(np.linalg.norm(text, axis=1, keepdims=True), 1e-9)
    conn.execute("DELETE FROM photo_labels WHERE source='clip'")
    rows = 0
    for start, block in index.chunks():
        scores = block @ text.T
        best = np.argsort(-scores, axis=1)[:, :top]
        batch = []
        for r in range(len(block)):
            item = int(index.ids[start + r])
            batch += [(item, labels[j].lower(), float(scores[r, j])) for j in best[r] if scores[r, j] >= min_score]
        conn.executemany("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,?,'clip')", batch)
        rows += len(batch)
    conn.commit()
    return rows
