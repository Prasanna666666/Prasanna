import sqlite3

import numpy as np
from PIL import Image

from aperture.db import MIGRATIONS
from aperture.indexing import faceattrs


class Embedder:
    """Fake image-search model: a bright crop looks like 'smiling' and 'child', a dark one like 'sad' and 'elderly'."""

    def embed_text(self, texts):
        out = np.zeros((len(texts), 2), np.float32)
        for i, t in enumerate(texts):
            out[i] = [1, 0] if ("smiling" in t or "child" in t) else ([0, 1] if ("sad" in t or "elderly" in t) else [0.5, 0.5])
        return out

    def preprocess(self, image):
        return float(np.asarray(image).mean())

    def embed_prepared(self, prepared):
        return np.array([[1, 0] if v > 100 else [0, 1] for v in prepared], np.float32)


def test_expression_and_age_group_are_read_from_saved_face_crops_and_become_searchable(tmp_path):
    conn = sqlite3.connect(":memory:")
    for s in MIGRATIONS:
        conn.executescript(s)
    for i in (1, 2):
        conn.execute("INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done) VALUES (?,?,?,?,?,?,1)", (i, f"/p/{i}", f"{i}", "image", 0, 0))
        (tmp_path / "faces").mkdir(exist_ok=True)
        Image.new("RGB", (20, 20), (230, 230, 230) if i == 1 else (10, 10, 10)).save(tmp_path / "faces" / f"{i}.jpg")
        conn.execute("INSERT INTO faces(id, item_id, emb, crop) VALUES (?,?,?,?)", (i, i, b"x", f"faces/{i}.jpg"))
    assert faceattrs.run(conn, tmp_path, Embedder()) == 2 and faceattrs.pending(conn) == []
    rows = {r[0]: r[1:] for r in conn.execute("SELECT face_id, expression, age FROM face_attributes")}
    assert rows[1] == ("smiling", "child") and rows[2] == ("sad", "elderly")
    labels = {(r[0], r[1]) for r in conn.execute("SELECT item_id, label FROM photo_labels WHERE source='face'")}
    assert {(1, "smiling"), (1, "child"), (2, "sad"), (2, "elderly")} <= labels
