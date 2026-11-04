"""Flags, trips and duplicates are worked out from what is already stored."""

import io
import json
import sqlite3

import numpy as np
from PIL import Image

from aperture.db import MIGRATIONS
from aperture.indexing import derive, details


def _db():
    conn = sqlite3.connect(":memory:")
    for script in MIGRATIONS:
        conn.executescript(script)
    return conn


def _item(conn, i, taken, place="", exif=1):
    conn.execute("INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif, place, place_text) VALUES (?,?,?,?,?,?,1,?,?,?,'')",
                 (i, f"/p/{i}.jpg", f"{i}.jpg", "image", 0, 0, taken, exif, place))


def test_iphone_capture_flags_are_found_in_the_stored_metadata():
    record = {"file": {"name": "Screenshot-fake.jpg"}, "exiftool": {"MakerNotes:ContentIdentifier": "ABC", "XMP:HDRGainMapVersion": 1},
              "pillow": {"exif": {"Exif": {"LensModel": "iPhone 12 front camera 2.7mm"}}}}
    flags = derive.meta_flags(record)
    assert {"live photo", "hdr", "front camera"} <= set(flags) and "screenshot" not in flags  # the file NAME never decides


def test_photos_are_grouped_into_trips_by_pauses_and_named_by_their_place():
    conn = _db()
    for i, (taken, place) in enumerate([("2026-03-01 10:00:00", "Shinjuku, Japan"), ("2026-03-01 18:00:00", "Shinjuku, Japan"),
                                        ("2026-03-02 09:00:00", "Chiyoda, Japan"), ("2026-06-10 12:00:00", "Eindhoven, The Netherlands"),
                                        ("2000-01-01 00:00:00", "Nowhere, X")], 1):
        _item(conn, i, taken, place)
    assert derive.build_events(conn) == 2  # the March trip and the June day; the year-2000 default date is ignored
    first = conn.execute("SELECT start, stop, n, place, country FROM events ORDER BY start").fetchone()
    assert first == ("2026-03-01", "2026-03-02", 3, "Shinjuku", "Japan")
    assert derive.build_events(conn) == 2  # rebuilding replaces, never duplicates


def test_a_word_finds_the_whole_trip_even_photos_without_gps():
    from aperture.agent.executor import Executor
    from aperture.agent.schema import Clause, Plan

    conn = _db()
    conn.row_factory = sqlite3.Row
    for i, taken in enumerate(["2026-03-01 10:00:00", "2026-03-01 15:00:00", "2026-03-02 09:00:00", "2026-07-01 09:00:00"], 1):
        _item(conn, i, taken)
    conn.execute("UPDATE items SET place='Shinjuku, Japan', place_text=' shinjuku tokyo japan' WHERE id=1")  # only photo 1 is known to be in Tokyo
    derive.build_events(conn)
    ex = Executor(conn, lambda: None, lambda: None)
    plan = Plan(intent="find", clauses=(Clause(engines=("place",), query="tokyo"),))
    groups = dict(ex.readings(plan))
    assert groups["Same trip as your tokyo photos"].tolist() == [1, 2, 3]


def _jpeg(color, size=(80, 60)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def test_the_perceptual_hash_matches_copies_and_re_saves():
    gradient = Image.linear_gradient("L").resize((90, 80)).convert("RGB")
    buf1, buf2 = io.BytesIO(), io.BytesIO()
    gradient.save(buf1, "JPEG", quality=95)
    gradient.resize((45, 40)).save(buf2, "JPEG", quality=60)  # a smaller, more compressed copy
    a, b = details.dhash(buf1.getvalue()), details.dhash(buf2.getvalue())
    assert a is not None and bin((a ^ b) & (2**64 - 1)).count("1") <= 6
    assert details.dhash(b"not an image") is None
