"""Expression and age group of every face, from the face crops the app already saved, using the image-search model (all offline).

The model is asked which description fits a face best ("a smiling face", "an elderly person"); no extra model is downloaded.
Confident results also become searchable photo labels (source 'face'), so "smiling" or "child" can be searched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

EXPRESSIONS = {
    "smiling": "a close-up photo of a smiling face", "laughing": "a close-up photo of a person laughing",
    "neutral": "a close-up photo of a face with a neutral expression", "serious": "a close-up photo of a serious face",
    "sad": "a close-up photo of a sad face", "angry": "a close-up photo of an angry face",
    "surprised": "a close-up photo of a surprised face", "eyes closed": "a close-up photo of a face with closed eyes",
}
AGES = {
    "baby": "a photo of a baby's face", "child": "a photo of a young child's face", "teenager": "a photo of a teenager's face",
    "young adult": "a photo of a young adult's face", "adult": "a photo of a middle-aged adult's face",
    "elderly": "a photo of an elderly person's face",
}
LABEL_MIN_P = 0.5  # only confident results become searchable labels
LOGIT_SCALE = 100.0  # CLIP's own temperature


def _unit(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)


def _softmax(scores: np.ndarray) -> np.ndarray:
    scores = scores - scores.max(axis=1, keepdims=True)
    e = np.exp(scores)
    return e / e.sum(axis=1, keepdims=True)


def pending(conn: sqlite3.Connection, limit: int = 0) -> list[tuple[int, int, str]]:
    sql = ("SELECT f.id, f.item_id, f.crop FROM faces f LEFT JOIN face_attributes a ON a.face_id=f.id "
           "WHERE a.face_id IS NULL AND f.crop IS NOT NULL ORDER BY f.id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [(r[0], r[1], r[2]) for r in conn.execute(sql)]


def run(conn: sqlite3.Connection, data_dir: Path, embedder: Any, limit: int = 0, stop: Any = None, batch: int = 32) -> int:
    """Read the expression and age group of every face that has none yet. Returns how many faces were read."""
    from PIL import Image

    expr_names, age_names = list(EXPRESSIONS), list(AGES)
    text = _unit(embedder.embed_text([*EXPRESSIONS.values(), *AGES.values()]).astype(np.float32))
    expr_text, age_text = text[: len(expr_names)], text[len(expr_names):]
    todo = pending(conn, limit)
    done = 0
    for start in range(0, len(todo), batch):
        if stop is not None and stop.is_set():
            break
        prepared, rows = [], []
        for face_id, item_id, crop in todo[start : start + batch]:
            try:
                with Image.open(data_dir / crop) as image:
                    prepared.append(embedder.preprocess(image.convert("RGB")))
                rows.append((face_id, item_id))
            except Exception:
                conn.execute("INSERT OR REPLACE INTO face_attributes VALUES (?,?,?,?,?)", (face_id, "unknown", 0.0, "unknown", 0.0))
        if not prepared:
            continue
        image_vecs = _unit(embedder.embed_prepared(prepared).astype(np.float32))
        p_expr = _softmax(LOGIT_SCALE * image_vecs @ expr_text.T)
        p_age = _softmax(LOGIT_SCALE * image_vecs @ age_text.T)
        for k, (face_id, item_id) in enumerate(rows):
            e, a = int(p_expr[k].argmax()), int(p_age[k].argmax())
            conn.execute("INSERT OR REPLACE INTO face_attributes VALUES (?,?,?,?,?)",
                         (face_id, expr_names[e], float(p_expr[k, e]), age_names[a], float(p_age[k, a])))
            for label, p in ((expr_names[e], p_expr[k, e]), (age_names[a], p_age[k, a])):
                if p >= LABEL_MIN_P:
                    conn.execute("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,?, 'face')", (item_id, label, float(p)))
            done += 1
        conn.commit()
    return done
