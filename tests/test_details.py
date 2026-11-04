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

    assert details.clip_tags(conn, index, Embedder(), ["Tokyo Tower", "beach"], top=1, min_score=0.5, verify=False) == 2
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


def test_a_word_found_as_a_place_gets_no_guesses_from_appearance_and_tags_match_exactly():
    from aperture.agent.executor import Executor
    from aperture.agent.schema import Clause, Plan

    conn = _db(4)
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE items SET gps_lat=35.68, gps_lon=139.76, place='Shinjuku, Japan', place_text=' shinjuku tokyo japan' WHERE id=1")
    conn.execute("INSERT INTO photo_labels VALUES (2, 'tokyo tower', 0.5, 'clip')")  # a landmark guess on a different photo
    ex = Executor(conn, lambda: None, lambda: None)
    assert ex._tag_ids("tokyo").tolist() == [] and ex._tag_ids("tokyo tower").tolist() == [2]  # exact label, not a part of one
    labels = [label for label, _ in ex.readings(Plan(intent="find", clauses=(Clause(engines=("place",), query="Shinjuku"),)))]
    assert labels == ["Taken in Shinjuku"] and not any("Looks like" in l or "Similar" in l for l in labels)
    lone = [label for label, _ in ex.readings(Plan(intent="find", clauses=(Clause(engines=("tag",), query="tokyo tower"),)))]
    assert lone == []  # a single look-alike clue with nothing else behind it is not shown
    conn.execute("UPDATE items SET meta_text=' tokyo tower' WHERE id=2")  # a second, independent clue (a folder name) agrees
    backed = [label for label, _ in ex.readings(Plan(intent="find", clauses=(Clause(engines=("tag",), query="tokyo tower"),)))]
    assert any("Looks like" in l or "folders named" in l for l in backed)  # backed by hard evidence: shown


def test_guesses_from_appearance_are_kept_only_when_something_independent_agrees():
    from aperture.search.embeddings import EmbeddingIndex
    from aperture.search.geo import GeoIndex

    conn = _db(4)
    # photo 1: really in Tokyo (GPS), photo 2: GPS in Amsterdam, photo 3: no GPS
    conn.execute("UPDATE items SET gps_lat=35.68, gps_lon=139.76 WHERE id=1")
    conn.execute("UPDATE items SET gps_lat=52.37, gps_lon=4.90 WHERE id=2")
    conn.execute("INSERT INTO photo_labels VALUES (4, 'dog', 0.9, 'vision')")  # photo 4: Apple Vision also sees a dog
    geo = GeoIndex(["Tokyo"], ["Japan"], [" tokyo japan"], np.array([35.68]), np.array([139.76]))
    vectors = np.ones((4, 2), np.float16)
    index = EmbeddingIndex(np.array([1, 2, 3, 4]), vectors)

    class Embedder:
        def embed_text(self, texts):
            return np.ones((len(texts), 2), np.float32)  # every photo matches every label equally well

    details.clip_tags(conn, index, Embedder(), ["Tokyo Tower", "dog"], top=2, min_score=0.0, min_p=0.0, geo=geo)
    tags = sorted(conn.execute("SELECT item_id, label FROM photo_labels WHERE source='clip'").fetchall())
    assert tags == [(1, "tokyo tower"), (4, "dog")]  # the Amsterdam photo, the photo without GPS and the dog-less photos are all dropped


def test_filler_words_are_not_looked_up_in_the_library():
    from aperture.search import quick

    conn = _db(2)
    seen = []
    originals = (quick.place_ids, quick.path_ids, quick.search_text_ids)
    quick.place_ids = lambda c, phrase: seen.append(phrase) or np.zeros(0, np.int64)
    quick.path_ids = quick.search_text_ids = lambda c, phrase: np.zeros(0, np.int64)
    try:
        quick.probe(conn, "show me the photos from this year of tokyo")
    finally:
        quick.place_ids, quick.path_ids, quick.search_text_ids = originals
    assert seen and all(p not in ("show", "the", "this", "year", "photos", "from") for p in seen) and "tokyo" in seen


def test_a_place_gives_one_combined_answer_of_everything_taken_in_or_near_it():
    from aperture.agent.executor import Executor
    from aperture.agent.schema import Clause, Plan
    from aperture.search.geo import GeoIndex

    conn = _db(3)
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE items SET gps_lat=35.18, gps_lon=136.90, place='Nagoya, Japan', place_text=' nagoya japan' WHERE id=1")
    conn.execute("UPDATE items SET gps_lat=35.0, gps_lon=137.0, place='Okazaki, Japan', place_text=' okazaki japan' WHERE id=2")  # near, named after a town
    geo = GeoIndex(["Nagoya"], ["Japan"], [" nagoya japan"], np.array([35.18]), np.array([136.90]))
    ex = Executor(conn, lambda: None, lambda: None, geo_provider=lambda: geo)
    readings = dict(ex.readings(Plan(intent="find", clauses=(Clause(engines=("place",), query="Nagoya"),))))
    assert readings["Taken in or near Nagoya"].tolist() == [1, 2]  # the place name alone would have found only photo 1
