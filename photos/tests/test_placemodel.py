"""A place recogniser learned from the library's own GPS photos, accepted only where it tested >= 80% accurate."""

import sqlite3
from datetime import datetime, timedelta

import numpy as np

from aperture.db import MIGRATIONS
from aperture.indexing import placemodel
from aperture.search.embeddings import EmbeddingIndex


def _library(per_city=300, seed=1):
    rng = np.random.default_rng(seed)
    conn = sqlite3.connect(":memory:")
    for script in MIGRATIONS:
        conn.executescript(script)
    cities = [(35.18, 136.90, np.array([1.0, 0.0, 0.0, 0.0])), (52.37, 4.90, np.array([0.0, 1.0, 0.0, 0.0]))]
    vectors, n = [], 0
    start = datetime(2024, 1, 1, 9, 0)
    for k in range(2 * per_city):  # GPS photos, one city per week, scenes at random hours
        lat, lon, base = cities[(k // 30) % 2]
        when = start + timedelta(days=k // 4, hours=(k * 7) % 10)
        n += 1
        conn.execute(
            "INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif, gps_lat, gps_lon) VALUES (?,?,?,?,?,?,1,?,1,?,?)",
            (n, f"/p/{n}", f"{n}", "image", 0, 0, when.isoformat(sep=" "), lat, lon),
        )
        vectors.append(base + rng.normal(0, 0.15, 4))
    easy, ambiguous = [], []
    for k in range(20):  # no GPS: look like city 0, taken far from any GPS photo in time
        n += 1
        when = datetime(2026, 1, 1) + timedelta(days=k)
        conn.execute(
            "INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif) VALUES (?,?,?,?,?,?,1,?,1)",
            (n, f"/p/{n}", f"{n}", "image", 0, 0, when.isoformat(sep=" ")),
        )
        vectors.append(cities[0][2] + rng.normal(0, 0.15, 4))
        easy.append(n)
    for k in range(20):  # no GPS: look like nothing in particular (equally like both)
        n += 1
        when = datetime(2026, 3, 1) + timedelta(days=k)
        conn.execute(
            "INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif) VALUES (?,?,?,?,?,?,1,?,1)",
            (n, f"/p/{n}", f"{n}", "image", 0, 0, when.isoformat(sep=" ")),
        )
        vectors.append((cities[0][2] + cities[1][2]) / 2 + rng.normal(0, 0.05, 4))
        ambiguous.append(n)
    index = EmbeddingIndex(np.arange(1, n + 1), np.array(vectors, np.float32))
    return conn, index, easy, ambiguous


def test_photos_that_look_like_a_known_place_are_located_and_ones_that_do_not_are_left_alone():
    from aperture.search.geo import GeoIndex

    conn, index, easy, ambiguous = _library()
    geo = GeoIndex(
        ["Nagoya", "Amsterdam"],
        ["Japan", "The Netherlands"],
        [" nagoya japan", " amsterdam the netherlands"],
        np.array([35.18, 52.37]),
        np.array([136.90, 4.90]),
    )
    report = placemodel.locate_by_picture(conn, index, geo)
    assert report["threshold"] is not None and report["accuracy_at_threshold"] >= 0.95 and report["tested"] > 100
    placed = dict(
        conn.execute(
            "SELECT id, gps_est_place FROM items WHERE id IN ({})".format(",".join(map(str, easy + ambiguous)))
        ).fetchall()
    )
    assert sum(placed[i] == "Nagoya, Japan" for i in easy) >= 15  # recognised by how they look
    assert sum(placed[i] is not None for i in ambiguous) <= 2  # a picture that fits both places equally is not guessed
    assert all(r[0] >= 0.95 for r in conn.execute("SELECT gps_est_conf FROM items WHERE gps_est_conf IS NOT NULL"))


def test_with_too_few_known_photos_nothing_is_guessed():
    conn = sqlite3.connect(":memory:")
    for script in MIGRATIONS:
        conn.executescript(script)
    index = EmbeddingIndex(np.zeros(0, np.int64), np.zeros((0, 4), np.float32))
    assert placemodel.locate_by_picture(conn, index, None)["located"] == 0


def test_a_place_is_trusted_only_if_it_tested_well_on_its_own():
    conn, index, _easy, _ambiguous = _library()
    report = placemodel.locate_by_picture(conn, index, None)
    assert (
        report["trusted_places"] == 2 and report["accuracy_at_threshold"] >= 0.95
    )  # both cities were tested often and recognised


def test_the_model_places_nothing_if_it_disagrees_with_photos_that_have_no_gps_but_a_trusted_location():
    conn, index, easy, _ambiguous = _library()
    rng = np.random.default_rng(5)
    n = len(index.ids)
    extra_ids, extra_vecs = [], []
    for k in range(150):  # no GPS, located by time to the OTHER city than they look like: the picture model must be wrong on them
        n += 1
        conn.execute(
            "INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif, gps_est_lat, gps_est_lon, gps_est_conf) VALUES (?,?,?,?,?,?,1,?,1,52.37,4.90,0.98)",
            (n, f"/p/{n}", f"{n}", "image", 0, 0, f"2026-06-{(k % 28) + 1:02d} 10:00:00"),
        )
        extra_ids.append(n)
        extra_vecs.append(np.array([1.0, 0.0, 0.0, 0.0]) + rng.normal(0, 0.15, 4))
    index = EmbeddingIndex(
        np.concatenate([index.ids, extra_ids]), np.vstack([index.vectors.astype(np.float32), np.array(extra_vecs, np.float32)])
    )
    report = placemodel.locate_by_picture(conn, index, None)
    assert report.get("blocked") is True and report["located"] == 0
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM items WHERE id IN ({}) AND gps_est_conf IS NOT NULL AND gps_est_place IS NOT NULL".format(
                ",".join(map(str, easy))
            )
        ).fetchone()[0]
        == 0
    )
