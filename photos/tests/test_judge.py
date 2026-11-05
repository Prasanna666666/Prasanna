"""The vision judge reads everything from undecided pictures, stores it for good, and places a photo only when something agrees."""

import json
import sqlite3

import numpy as np

from aperture.db import MIGRATIONS, meta_get
from aperture.indexing import judge
from aperture.search.geo import GeoIndex


def _db():
    conn = sqlite3.connect(":memory:")
    for script in MIGRATIONS:
        conn.executescript(script)
    return conn


def _photo(conn, i, taken, gps=None):
    conn.execute(
        "INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif, gps_lat, gps_lon) VALUES (?,?,?,?,?,?,1,?,1,?,?)",
        (i, f"/p/{i}", f"{i}", "image", 0, 0, taken, gps[0] if gps else None, gps[1] if gps else None),
    )


class Fake:
    """A vision model that says every picture is Tokyo Tower in Tokyo, and records what it was asked."""

    def __init__(self, city="Tokyo", sure=True):
        self.city, self.sure, self.calls = city, sure, 0

    def extract(self, image, prompt, schema, max_tokens=700):
        self.calls += 1
        return json.dumps(
            {
                "caption": "A red tower at dusk",
                "scene": "city skyline",
                "objects": ["Tower", "Cars"],
                "landmarks": ["Tokyo Tower"],
                "place": {"city": self.city, "country": "Japan", "evidence": "the tower", "sure": self.sure},
                "time_of_day": "dusk",
            }
        )


GEO = GeoIndex(
    ["Tokyo", "Nagoya"],
    ["Japan", "Japan"],
    [" tokyo japan", " nagoya japan"],
    np.array([35.68, 35.18]),
    np.array([139.76, 136.90]),
)


def _previews(tmp_path, ids):
    from PIL import Image

    from aperture.config import preview_rel

    for i in ids:
        path = tmp_path / preview_rel(i)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 30), (200, 10, 10)).save(path, "JPEG")


def test_everything_the_judge_reads_is_stored_for_good_and_becomes_searchable(tmp_path):
    conn = _db()
    _photo(conn, 1, "2026-03-01 10:00:00", gps=(35.68, 139.76))  # GPS photo in Tokyo, the same afternoon
    _photo(conn, 2, "2026-03-01 15:00:00")  # no GPS
    _previews(tmp_path, [1, 2])
    vision = Fake()
    out = judge.run(conn, tmp_path, vision, GEO)
    assert out["analysed"] == 1 and vision.calls == 1  # only the undecided photo is looked at
    data = json.loads(conn.execute("SELECT data FROM photo_vision WHERE item_id=2").fetchone()[0])
    assert data["caption"] == "A red tower at dusk" and data["landmarks"] == ["Tokyo Tower"]
    assert {r[0] for r in conn.execute("SELECT label FROM photo_labels WHERE item_id=2 AND source='judge'")} >= {
        "tower",
        "tokyo tower",
        "city skyline",
        "dusk",
    }
    assert judge.pending(conn) == []  # analysed once, never again


def test_the_judges_place_is_accepted_only_when_the_photos_around_it_agree(tmp_path):
    conn = _db()
    _photo(conn, 1, "2026-03-01 10:00:00", gps=(35.18, 136.90))  # the day was spent in Nagoya
    _photo(conn, 2, "2026-03-01 15:00:00")
    _previews(tmp_path, [1, 2])
    out = judge.run(conn, tmp_path, Fake(city="Tokyo"), GEO)  # the judge says Tokyo: it disagrees with the day's photos
    assert (
        out["analysed"] == 1
        and out["located"] == 0
        and conn.execute("SELECT gps_est_lat FROM items WHERE id=2").fetchone()[0] is None
    )
    conn.execute("DELETE FROM photo_vision")
    out = judge.run(conn, tmp_path, Fake(city="Nagoya"), GEO)  # it agrees
    assert out["located"] == 1 and conn.execute("SELECT gps_est_place FROM items WHERE id=2").fetchone()[0].startswith("Nagoya")


def test_with_nothing_nearby_the_judge_alone_counts_only_after_it_measured_at_least_80_percent(tmp_path):
    conn = _db()
    for i in range(
        1, 11
    ):  # ten GPS photos in Tokyo, months before: they are not "around that time", so they can only be used to measure
        _photo(conn, i, f"2025-01-{i:02d} 10:00:00", gps=(35.68, 139.76))
    _photo(conn, 99, "2026-09-01 10:00:00")  # no GPS and nothing else that day
    _previews(tmp_path, [*list(range(1, 11)), 99])
    assert judge.run(conn, tmp_path, Fake(), GEO, limit=1)["located"] == 0  # never measured: not trusted
    conn.execute("DELETE FROM photo_vision")
    result = judge.calibrate(conn, tmp_path, Fake(), GEO, samples=10)
    assert result["precision"] == 1.0 and float(meta_get(conn, "judge_precision")) == 1.0
    assert judge.run(conn, tmp_path, Fake(), GEO)["located"] == 1  # measured 100%: the judge's answer is accepted
    wrong = judge.calibrate(conn, tmp_path, Fake(city="Nagoya"), GEO, samples=10)
    assert wrong["precision"] == 0.0  # a judge that names the wrong city is measured as such and no longer trusted
