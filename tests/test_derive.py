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


def test_the_place_report_gives_the_numbers_behind_a_place_name():
    from aperture.indexing import placereport
    from aperture.search.geo import GeoIndex

    conn = _db()
    _item(conn, 1, "2026-03-01 10:00:00", "Nagoya, Japan")
    conn.execute("UPDATE items SET gps_lat=35.18, gps_lon=136.90, place_text=' nagoya japan' WHERE id=1")
    _item(conn, 2, "2026-03-01 18:00:00")  # same trip, no GPS (a screenshot)
    derive.build_events(conn)
    geo = GeoIndex(["Nagoya"], ["Japan"], [" nagoya japan"], np.array([35.18]), np.array([136.90]))
    text = "\n".join(placereport.report(conn, geo, "Nagoya"))
    assert "1 with GPS" in text and "says 'Nagoya': 1" in text and "within 25 km of Nagoya, Japan: 1" in text
    assert "Trip photos around those: 2 (1 without GPS, 1 with GPS)" in text


def test_the_gps_audit_separates_missing_in_the_file_from_failed_to_read():
    from aperture.indexing import placereport

    conn = _db()
    _item(conn, 1, "2026-03-01 10:00:00")  # the file has GPS but the index does not: the app failed to read it
    _item(conn, 2, "2026-03-01 11:00:00")  # genuinely no GPS in the file
    conn.execute("UPDATE items SET camera='iPhone 12' WHERE id IN (1,2)")
    conn.execute("INSERT INTO file_metadata VALUES (1, 1, 'a', ?, 0)", (json.dumps({"exiftool": {"GPS:GPSLatitude": 35.1}}),))
    conn.execute("INSERT INTO file_metadata VALUES (2, 1, 'b', ?, 0)", (json.dumps({"pillow": {"exif": {}}}),))
    lines = placereport._gps_audit(conn)
    assert "failed to read it): 1" in lines[0] and "iPhone 12 (2)" in lines[1]


def test_photos_without_gps_get_a_location_only_from_guesses_that_tested_at_least_80_percent_accurate():
    from datetime import datetime, timedelta

    from aperture.search.geo import GeoIndex

    conn = _db()
    geo = GeoIndex(["Nagoya", "Amsterdam"], ["Japan", "The Netherlands"], [" nagoya japan", " amsterdam the netherlands"],
                   np.array([35.18, 52.37]), np.array([136.90, 4.90]))
    place = {0: (35.18, 136.90), 1: (52.37, 4.90)}
    n = 0
    start = datetime(2025, 1, 1, 10, 0)
    for day in range(40):  # one city per day, far apart; eight photos ten minutes apart
        for k in range(8):
            n += 1
            lat, lon = place[day % 2]
            when = start + timedelta(days=day, minutes=10 * k)
            conn.execute("INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif, gps_lat, gps_lon) VALUES (?,?,?,?,?,?,1,?,1,?,?)",
                         (n, f"/p/{n}", f"{n}", "image", 0, 0, when.isoformat(sep=" "), lat, lon))
    easy, hard = 1000, 1001  # no GPS: between two photos ten minutes apart (day 5, Amsterdam), and in the dead of night between two cities
    for item_id, when in ((easy, start + timedelta(days=5, minutes=35)), (hard, start + timedelta(days=5, hours=14))):
        conn.execute("INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done, taken_at, taken_exif) VALUES (?,?,?,?,?,?,1,?,1)",
                     (item_id, f"/p/{item_id}", f"{item_id}", "image", 0, 0, when.isoformat(sep=" ")))
    outcome = derive.infer_locations(conn, geo)
    used = {k["kind"]: k for k in outcome["kinds"]}
    assert used["neighbours agree, within 10 min"]["used"] and used["neighbours agree, within 10 min"]["accuracy"] >= 0.95
    got = dict(conn.execute("SELECT id, gps_est_place FROM items WHERE id IN (1000, 1001)").fetchall())
    assert got[easy] == "Amsterdam, The Netherlands" and got[hard] is None  # the doubtful guess is not made: it does not belong
    assert outcome["located"] >= 1 and conn.execute("SELECT gps_est_conf FROM items WHERE id=1000").fetchone()[0] >= 0.95


def test_a_trip_never_reaches_another_country_even_without_a_pause_in_the_photos():
    from aperture.agent.executor import Executor
    from aperture.agent.schema import Clause, Plan

    conn = _db()
    conn.row_factory = sqlite3.Row
    legs = [(1, "2026-03-01 10:00:00", 35.68, 139.76, "Shinjuku, Japan"), (2, "2026-03-01 20:00:00", 35.68, 139.76, "Shinjuku, Japan"),
            (3, "2026-03-02 08:00:00", 64.14, -21.90, "Reykjavik, Iceland"), (4, "2026-03-02 20:00:00", 64.14, -21.90, "Reykjavik, Iceland")]
    for i, taken, la, lo, place in legs:  # photos every few hours: no 36-hour pause anywhere
        _item(conn, i, taken, place)
        conn.execute("UPDATE items SET gps_lat=?, gps_lon=?, place_text=? WHERE id=?", (la, lo, f" {place.lower().replace(',', '')}", i))
    assert derive.build_events(conn) == 2  # Japan and Iceland are separate trips
    ex = Executor(conn, lambda: None, lambda: None)
    assert ex._trip_ids(np.array([1])).tolist() == [1, 2]
    assert ex._near_the_anchors(np.array([1, 2, 3, 4]), np.array([1])).tolist() == [1, 2]  # and even a stray Iceland photo is dropped


def test_explain_shows_every_reading_with_the_places_its_photos_are_really_from(capsys):
    import argparse
    from types import SimpleNamespace

    from aperture import cli
    from aperture.search.geo import GeoIndex

    conn = _db()
    conn.row_factory = sqlite3.Row
    _item(conn, 1, "2026-03-01 10:00:00", "Shinjuku, Japan")
    conn.execute("UPDATE items SET gps_lat=35.68, gps_lon=139.76, place_text=' shinjuku tokyo japan' WHERE id=1")
    _item(conn, 2, "2026-03-01 11:00:00", "Reykjavik, Iceland")
    conn.execute("UPDATE items SET gps_lat=64.14, gps_lon=-21.90, place_text=' reykjavik iceland' WHERE id=2")
    geo = GeoIndex(["Tokyo"], ["Japan"], [" tokyo japan"], np.array([35.68]), np.array([139.76]))
    class Keep:  # the test connection must survive the command closing it
        def __getattr__(self, name):
            return (lambda: None) if name == "close" else getattr(conn, name)

    ctx = SimpleNamespace(db=SimpleNamespace(connect=lambda: Keep()), embedding_index=lambda: None, search_embedder=lambda: None, geo=lambda: geo)
    cli.cmd_explain(ctx, argparse.Namespace(words=["Tokyo"]))
    out = capsys.readouterr().out
    assert "Taken in or near Tokyo" in out and "Shinjuku, Japan" in out and "Iceland" not in out


def test_a_photo_without_a_location_joins_a_trip_only_if_its_camera_also_took_located_photos_there():
    from aperture.agent.executor import Executor

    conn = _db()
    conn.row_factory = sqlite3.Row
    for i, camera, gps in ((1, "iPhone 12", (35.68, 139.76)), (2, "iPhone 12", None), (3, "Canon EOS R100", None)):
        _item(conn, i, f"2026-03-01 1{i}:00:00")
        conn.execute("UPDATE items SET camera=?, gps_lat=?, gps_lon=? WHERE id=?", (camera, gps[0] if gps else None, gps[1] if gps else None, i))
    derive.build_events(conn)
    ex = Executor(conn, lambda: None, lambda: None)
    # the iPhone screenshot-like photo (no GPS) shares a camera with a located photo: kept. The Canon never records GPS: its clock is unproven: dropped.
    assert ex._trip_ids(np.array([1])).tolist() == [1, 2]


def test_a_worked_out_location_does_not_prove_a_cameras_clock():
    from aperture.agent.executor import Executor

    conn = _db()
    conn.row_factory = sqlite3.Row
    for i, camera, gps, est in ((1, "iPhone 12", (35.68, 139.76), None), (2, "Canon EOS R100", None, (35.68, 139.76)), (3, "Canon EOS R100", None, None)):
        _item(conn, i, f"2026-03-01 1{i}:00:00")
        conn.execute("UPDATE items SET camera=?, gps_lat=?, gps_lon=?, gps_est_lat=?, gps_est_lon=? WHERE id=?",
                     (camera, gps[0] if gps else None, gps[1] if gps else None, est[0] if est else None, est[1] if est else None, i))
    derive.build_events(conn)
    ex = Executor(conn, lambda: None, lambda: None)
    # photo 2 was placed (estimated), photo 3 was not: the Canon never recorded GPS, so photo 3 stays out of the iPhone's trip
    assert ex._trip_ids(np.array([1, 2])).tolist() == [1, 2]
