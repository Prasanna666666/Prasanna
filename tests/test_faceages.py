"""The age model's estimates become searchable labels only where they are clearly inside a group."""

import sqlite3

from PIL import Image

from aperture.db import MIGRATIONS
from aperture.indexing import faceages
from aperture.ml.age import age_group


def test_an_estimate_near_a_boundary_gets_no_group():
    assert age_group(1.2) == "baby" and age_group(7) == "child" and age_group(16) == "teenager" and age_group(27) == "young adult"
    assert age_group(45) == "adult" and age_group(70) == "elderly"
    assert age_group(3) is None and age_group(12.5) is None and age_group(35) is None  # between groups: not guessed


class Fake:
    def estimate(self, image):
        return float(image.size[0])  # the crop's width stands in for the age


def test_ages_are_estimated_from_saved_crops_and_clear_ones_become_trusted_labels(tmp_path):
    conn = sqlite3.connect(":memory:")
    for s in MIGRATIONS:
        conn.executescript(s)
    (tmp_path / "faces").mkdir()
    for i, years in ((1, 1), (2, 3), (3, 30)):  # a baby, someone in between groups, a young adult
        conn.execute("INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done) VALUES (?,?,?,?,?,?,1)", (i, f"/p/{i}", f"{i}", "image", 0, 0))
        Image.new("RGB", (years, 8), (9, 9, 9)).save(tmp_path / "faces" / f"{i}.png")
        conn.execute("INSERT INTO faces(id, item_id, emb, crop) VALUES (?,?,?,?)", (i, i, b"x", f"faces/{i}.png"))
    assert faceages.run(conn, tmp_path, Fake()) == 3 and faceages.pending(conn) == []
    assert faceages.make_labels(conn) == 2
    labels = {(r[0], r[1], r[2]) for r in conn.execute("SELECT item_id, label, score FROM photo_labels WHERE source='age'")}
    assert labels == {(1, "baby", 0.85), (3, "young adult", 0.85)}  # photo 2 sits between groups: no label
