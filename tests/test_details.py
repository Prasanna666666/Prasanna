"""What is IN each picture is read once and stored; later questions are database lookups."""

import sqlite3

import numpy as np

from aperture.db import MIGRATIONS
from aperture.indexing import details
from aperture.ml.vision_details import Details, to_box


def _db(n=3):
    conn = sqlite3.connect(":memory:")
    for script in MIGRATIONS:
        conn.executescript(script)
    for i in range(1, n + 1):
        conn.execute("INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done) VALUES (?,?,?,?,?,?,1)", (i, f"/p/{i}.jpg", f"{i}.jpg", "image", 0, 0))
    return conn


class Fake:
    def analyse(self, data):
        return Details(labels=[("Dog", 0.9)], objects=[("animal", "Dog", 0.8, (0.1, 0.2, 0.5, 0.9))], texts=[("EXIT", 0.99, (0.0, 0.0, 0.2, 0.1))])


def test_vision_boxes_are_converted_to_top_left_fractions():
    assert to_box((0.1, 0.2, 0.3, 0.4)) == (0.1, 0.4, 0.4, 0.8)  # Vision's origin is the bottom left


def test_every_picture_gets_labels_objects_and_text_with_places(tmp_path):
    conn = _db()
    for i in (1, 2, 3):
        d = tmp_path / "previews" / "0000"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{i}.jpg").write_bytes(b"x")
    done, bad = details.run(conn, tmp_path, Fake())
    assert (done, bad) == (3, 0) and details.pending(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM photo_labels WHERE label='dog'").fetchone()[0] == 3
    assert conn.execute("SELECT x1, y2 FROM photo_objects WHERE item_id=1").fetchone() == (0.1, 0.9)
    assert conn.execute("SELECT text FROM photo_text WHERE item_id=2").fetchone()[0] == "EXIT"


def test_an_unreadable_preview_is_recorded_and_the_pass_goes_on(tmp_path):
    conn = _db(2)
    (tmp_path / "previews" / "0000").mkdir(parents=True)
    (tmp_path / "previews" / "0000" / "2.jpg").write_bytes(b"x")  # item 1 has no preview
    assert details.run(conn, tmp_path, Fake()) == (1, 1)
    assert "FileNotFoundError" in conn.execute("SELECT notes FROM photo_details WHERE item_id=1").fetchone()[0]


def test_scene_and_landmark_tags_come_from_the_stored_embeddings_without_decoding_images():
    from aperture.search.embeddings import EmbeddingIndex

    conn = _db(2)
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], np.float16)
    index = EmbeddingIndex(np.array([1, 2]), vectors)

    class Embedder:
        def embed_text(self, texts):
            return np.array([[1.0, 0.0] if "tower" in t.lower() else [0.0, 1.0] for t in texts], np.float32)

    assert details.clip_tags(conn, index, Embedder(), ["Tokyo Tower", "beach"], top=1, min_score=0.5) == 2
    tags = dict(conn.execute("SELECT item_id, label FROM photo_labels WHERE source='clip'").fetchall())
    assert tags == {1: "tokyo tower", 2: "beach"}


def test_the_vocabulary_ships_with_the_app_and_includes_landmarks():
    words = details.vocabulary()
    assert "Tokyo Tower" in words and "dog" in words and len(words) > 150


def test_labels_are_searchable_as_a_reading_of_a_word():
    from aperture.agent.executor import Executor

    conn = _db(3)
    conn.execute("INSERT INTO photo_labels VALUES (2, 'tokyo tower', 0.4, 'clip')")
    conn.row_factory = sqlite3.Row
    ex = Executor(conn, lambda: None, lambda: None)
    assert ex._tag_ids("Tokyo Tower").tolist() == [2] and ex._tag_ids("zzz").tolist() == []
