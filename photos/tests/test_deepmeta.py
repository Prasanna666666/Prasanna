"""Every detail a photo carries is read once and stored for good."""

import json
import sqlite3
from pathlib import Path

from PIL import Image

from aperture.indexing import deepmeta


def _photo_with_exif(path: Path) -> Path:
    image = Image.new("RGB", (64, 48), (200, 30, 30))
    exif = Image.Exif()
    exif[271], exif[272] = "Apple", "iPhone 12"
    exif[306] = "2026:03:04 10:11:12"
    exif.get_ifd(0x8769)[36867] = "2026:03:04 10:11:12"
    exif.get_ifd(0x8769)[0x829A] = 0.01
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (35.0, 40.0, 48.0), "E", (139.0, 45.0, 36.0)
    image.save(path, "JPEG", exif=exif)
    return path


def test_every_exif_directory_is_kept_with_readable_names(tmp_path):
    record = deepmeta.read_all(_photo_with_exif(tmp_path / "a.jpg"))
    exif = record["pillow"]["exif"]
    assert exif["Make"] == "Apple" and exif["Model"] == "iPhone 12"
    assert exif["Exif"]["DateTimeOriginal"] == "2026:03:04 10:11:12" and exif["Exif"]["ExposureTime"] == 0.01
    assert exif["GPS"]["GPSLatitudeRef"] == "N" and len(exif["GPS"]["GPSLatitude"]) == 3
    assert record["pillow"]["size"] == [64, 48] and record["file"]["bytes"] > 0 and len(record["file"]["sha256"]) == 64


def test_a_reader_that_fails_never_loses_what_the_others_found(tmp_path):
    broken = tmp_path / "x.jpg"
    broken.write_bytes(b"not an image")
    record = deepmeta.read_all(broken)
    assert "pillow" in record["errors"] and record["file"]["bytes"] == 12  # the file facts survive


def test_large_binary_values_are_summarised_not_dropped():
    assert deepmeta.json_safe(b"x" * 10000)["bytes"] == 10000
    assert deepmeta.json_safe(b"ab") == {"bytes_b64": "YWI="}
    assert json.dumps(deepmeta.json_safe({"a": (1, 2.5, b"z", {3})}))  # always serialisable


def test_the_pass_is_resumable_and_stores_one_record_per_photo(tmp_path):
    from aperture.db import MIGRATIONS

    conn = sqlite3.connect(":memory:")
    for script in MIGRATIONS:
        conn.executescript(script)
    photo = _photo_with_exif(tmp_path / "a.jpg")
    for i, p in enumerate([photo, tmp_path / "gone.jpg"], 1):
        conn.execute(
            "INSERT INTO items(id, path, rel_path, kind, mtime, size) VALUES (?,?,?,?,?,?)", (i, str(p), p.name, "image", 0, 0)
        )
    assert [i for i, _ in deepmeta.pending(conn)] == [1, 2]
    assert deepmeta.run(conn)[0] == 2
    assert deepmeta.pending(conn) == []  # nothing left: a second run reads nothing
    data = json.loads(conn.execute("SELECT data FROM file_metadata WHERE item_id=1").fetchone()[0])
    assert data["pillow"]["exif"]["Make"] == "Apple"
    assert conn.execute("SELECT sha256 FROM file_metadata WHERE item_id=1").fetchone()[0]
