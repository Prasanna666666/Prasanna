import numpy as np
import pytest

from aperture.agent.schema import plan_from_raw
from aperture.search.filters import Filters, apply_filters
from aperture.search.geo import GeoIndex

from .test_agent import plan, service


@pytest.fixture
def photos(scanned):
    """Five photos with known capture times, sizes and places."""
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items ORDER BY id")]
    rows = [
        # id, taken_at, exif, w, h, lat, lon
        (ids[0], "2024-06-01 21:30:00", 1, 4000, 3000, 51.44, 5.47),  # Saturday night, Eindhoven
        (ids[1], "2024-06-03 09:15:00", 1, 3000, 4000, 51.45, 5.48),  # Monday morning, Eindhoven
        (ids[2], "2024-06-04 02:00:00", 1, 3000, 3000, 52.37, 4.90),  # Tuesday 2am (night), Amsterdam
        (ids[3], "2024-06-08 14:00:00", 0, 4000, 3000, None, None),  # Saturday, file date only
        (ids[4], "2024-06-09 18:45:00", 1, 4000, 3000, None, None),  # Sunday evening
    ]
    for i, t, ex, w, h, la, lo in rows:
        conn.execute(
            "UPDATE items SET taken_at=?, taken_exif=?, width=?, height=?, gps_lat=?, gps_lon=? WHERE id=?",
            (t, ex, w, h, la, lo, i),
        )
    conn.commit()
    return scanned, conn, ids


def ids_for(conn, **kw):
    found, _ = apply_filters(conn, Filters(**kw), None)
    return set(found.tolist())


def test_time_of_day_wraps_midnight_and_ignores_file_dates(photos):
    _, conn, ids = photos
    assert ids_for(conn, time_of_day="night") == {ids[0], ids[2]}
    assert ids_for(conn, time_of_day="afternoon") == set()  # ids[3] has no camera time: not guessed
    assert ids_for(conn, time_of_day="evening") == {ids[4]}
    assert ids_for(conn, hour_from=8, hour_to=10) == {ids[1]}


def test_weekend_orientation_gps(photos):
    _, conn, ids = photos
    assert ids_for(conn, day_type="weekend") == {ids[0], ids[3], ids[4]}
    assert ids_for(conn, day_type="weekday") == {ids[1], ids[2]}
    assert ids_for(conn, orientation="portrait") == {ids[1]}
    assert ids_for(conn, orientation="square") == {ids[2]}
    assert ids_for(conn, has_gps="yes") == set(ids[:3])
    assert ids_for(conn, time_of_day="night", day_type="weekend") == {ids[0]}


def test_people_count_uses_faces(photos):
    _, conn, ids = photos  # the fake analyser found exactly one face per photo
    assert ids_for(conn, min_people=1, max_people=1) == set(ids)
    assert ids_for(conn, min_people=2) == set()
    assert ids_for(conn, max_people=0) == set()


def test_near_place_with_offline_geo(photos, tmp_path):
    _, conn, ids = photos
    cities = tmp_path / "cities.txt"

    def row(gid, name, lat, lon, pop):
        return "\t".join([str(gid), name, name, "", str(lat), str(lon), "P", "PPL", "NL", "", "", "", "", "", str(pop)])

    cities.write_text("\n".join([row(1, "Eindhoven", 51.44, 5.47, 230000), row(2, "Amsterdam", 52.37, 4.90, 870000)]))
    geo = GeoIndex.from_files(cities, None)
    found, notes = apply_filters(conn, Filters(near="Eindhoven", radius_km=10), geo)
    assert set(found.tolist()) == {ids[0], ids[1]}
    wide, _ = apply_filters(conn, Filters(near="Eindhoven", radius_km=300), geo)
    assert set(wide.tolist()) == set(ids[:3])
    unknown, notes = apply_filters(conn, Filters(near="Atlantis"), geo)
    assert len(unknown) == 0 and any("Atlantis" in n for n in notes)
    none, notes = apply_filters(conn, Filters(near="Eindhoven"), None)
    assert len(none) == 0 and notes


def test_filters_coercion_is_lenient():
    p, _ = plan_from_raw(
        {
            "intent": "find",
            "filters": {"time_of_day": "Evening", "min_people": "3", "hour_from": 30, "orientation": 5, "near": "Rome"},
        }
    )
    f = p.filters
    assert (f.time_of_day, f.min_people, f.hour_from, f.orientation, f.near) == ("evening", 3, -1, "none", "Rome")
    assert plan_from_raw({"filters": "garbage"})[0].filters.is_empty
    assert plan_from_raw({"intent": "find", "filters": {"day_type": "weekend"}})[0].has_constraints


def test_agent_applies_filters_end_to_end(photos):
    ctx, _, ids = photos
    svc, _ = service(ctx, plan(filters={"time_of_day": "night", "day_type": "weekend"}))
    reply = svc.ask("weekend nights")
    assert reply.ids.tolist() == [ids[0]] and "weekend" in reply.text
    svc, _ = service(ctx, plan(filters={"time_of_day": "night"}, clauses=[{"engines": ["visual"], "query": "green frog"}]))
    night = svc.ask(
        "green frogs at night"
    )  # no night photo shows a green frog: the filter stays, only the look is relaxed, and it says so
    only_night, _ = service(ctx, plan(filters={"time_of_day": "night"}))
    night_photos = set(only_night.ask("at night").ids.tolist())
    assert any("No photo clearly shows green frog" in n for n in night.notes)
    assert night.ids.size and set(night.ids.tolist()) <= night_photos  # every photo shown really was taken at night
    assert isinstance(reply.ids, np.ndarray)
