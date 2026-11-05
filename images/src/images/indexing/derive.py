"""Facts worked out from what was already stored: iPhone capture flags and trips/events. No file is read."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

MIN_PRECISION = 0.95  # a location is given to a photo only when that kind of guess measured at least this accurate on the library's own GPS photos
TRIP_JUMP_KM = 200.0  # photos this far apart cannot belong to the same trip leg
EVENT_GAP = timedelta(hours=36)  # a pause this long between photos starts a new trip or occasion


def meta_flags(record: dict) -> list[str]:
    """Capture flags found in a stored metadata record (maker notes, XMP, lens name). Case-insensitive, tolerant of tag names."""
    body = dict(record)
    body.pop("file", None)  # the file name must not decide (a file called Screenshot)
    text = json.dumps(body, ensure_ascii=False).lower()
    flags: list[str] = []
    for flag, needles in (
        ("live photo", ("contentidentifier", "livephoto")),
        ("burst", ("burstuuid", "burstid")),
        ("screenshot", ("screenshot",)),
        ("portrait mode", ("portraiteffects", "portrait")),
        ("hdr", ("hdrgain", "hdrimage", '"hdr"')),
        ("panorama", ("panorama",)),
        ("night mode", ("nightmode", "night mode")),
    ):
        if any(n in text for n in needles):
            flags.append(flag)
    lens = str((record.get("pillow", {}).get("exif", {}).get("Exif", {}) or {}).get("LensModel", "")).lower()
    if "front" in lens:
        flags.append("front camera")
    elif "back" in lens or "rear" in lens:
        flags.append("back camera")
    return flags


def derive_meta_labels(conn: sqlite3.Connection) -> int:
    """Turn the stored metadata into searchable labels (source 'meta')."""
    conn.execute("DELETE FROM photo_labels WHERE source='meta'")
    rows = 0
    batch: list[tuple[int, str]] = []
    for item_id, data in conn.execute("SELECT item_id, data FROM file_metadata"):
        try:
            batch += [(item_id, flag) for flag in meta_flags(json.loads(data))]
        except ValueError:
            continue
        if len(batch) >= 5000:
            conn.executemany("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,1.0,'meta')", batch)
            rows += len(batch)
            batch = []
    conn.executemany("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,1.0,'meta')", batch)
    conn.commit()
    return rows + len(batch)


def build_events(conn: sqlite3.Connection, gap: timedelta = EVENT_GAP) -> int:
    """Group photos into trips/occasions: consecutive photos (by camera date) with no pause longer than `gap`. Rebuilt each time."""
    rows = conn.execute(
        "SELECT id, taken_at, place, gps_lat, gps_lon FROM items WHERE missing=0 AND meta_done=1 AND taken_exif=1 AND taken_at >= '2003' ORDER BY taken_at"
    ).fetchall()
    conn.execute("DELETE FROM photo_events")
    conn.execute("DELETE FROM events")
    groups: list[list[tuple[int, str, str]]] = []
    last = None
    where: tuple[float, float] | None = None  # the last known position
    for item_id, taken, place, lat, lon in rows:
        try:
            when = datetime.fromisoformat(str(taken)[:19])
        except ValueError:
            continue
        moved = False
        if lat is not None and lon is not None:
            if where is not None and float(_haversine(where[0], where[1], lat, lon)) > TRIP_JUMP_KM:
                moved = (
                    True  # a trip is one place: a jump of hundreds of kilometres starts a new one, even with no pause in between
                )
            where = (lat, lon)
        if last is None or when - last > gap or moved:
            groups.append([])
        groups[-1].append((item_id, str(taken)[:10], place or ""))
        last = when
    for group in groups:
        places = Counter(p for _, _, p in group if p)
        top = places.most_common(1)[0][0] if places else ""
        city, _, country = top.rpartition(", ")
        cursor = conn.execute(
            "INSERT INTO events(start, stop, n, place, country) VALUES (?,?,?,?,?)",
            (group[0][1], group[-1][1], len(group), city or top, country if city else ""),
        )
        conn.executemany("INSERT INTO photo_events(item_id, event_id) VALUES (?,?)", [(i, cursor.lastrowid) for i, _, _ in group])
    conn.commit()
    return len(groups)


# ---------------------------------------------------------------------------------------------------------------------------
# Photos without GPS
# ---------------------------------------------------------------------------------------------------------------------------
GAP_EDGES_MIN = (10, 60, 360, 1440)  # minutes to the nearest photo that has GPS
RADIUS_KM = 25.0


def _haversine(lat1, lon1, lat2, lon2):
    import numpy as np

    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _guess(times, t_gps, lat_gps, lon_gps, before, after):
    """For each query time: (bucket, predicted lat, predicted lon). A bucket is (neighbours agree?, how close in time); -1 = no guess."""
    import numpy as np

    n = len(times)
    bucket = np.full(n, -1, np.int64)
    plat, plon = np.full(n, np.nan), np.full(n, np.nan)
    has_b, has_a = before >= 0, after < len(t_gps)
    gap_b = np.where(has_b, times - t_gps[np.clip(before, 0, len(t_gps) - 1)], np.inf)
    gap_a = np.where(has_a, t_gps[np.clip(after, 0, len(t_gps) - 1)] - times, np.inf)
    lb, ob = lat_gps[np.clip(before, 0, len(t_gps) - 1)], lon_gps[np.clip(before, 0, len(t_gps) - 1)]
    la, oa = lat_gps[np.clip(after, 0, len(t_gps) - 1)], lon_gps[np.clip(after, 0, len(t_gps) - 1)]
    both = has_b & has_a
    agree = both & (_haversine(lb, ob, la, oa) <= RADIUS_KM)
    use_b = gap_b <= gap_a
    gap = np.where(
        agree, np.maximum(gap_b, gap_a), np.minimum(gap_b, gap_a)
    )  # agreeing neighbours: the farther one still has to be close
    plat, plon = np.where(use_b, lb, la), np.where(use_b, ob, oa)
    edge = np.searchsorted(np.array(GAP_EDGES_MIN, float), gap, side="left")  # 0..len(edges); len(edges) = too far apart
    ok = edge < len(GAP_EDGES_MIN)
    bucket = np.where(ok, edge + np.where(agree, 0, len(GAP_EDGES_MIN)), -1)
    return bucket, plat, plon


def infer_locations(conn: sqlite3.Connection, geo, min_precision: float = MIN_PRECISION, min_samples: int = 30) -> dict:
    """Give photos with no GPS a location from the photos around them in time, but only for kinds of guess that are at least
    `min_precision` accurate when tested on the library's own GPS photos (each is hidden in turn and guessed from its neighbours).
    Returns the measured accuracy of every kind and how many photos were located."""
    import numpy as np

    rows = conn.execute(
        "SELECT id, taken_at, gps_lat, gps_lon FROM items WHERE missing=0 AND meta_done=1 AND taken_exif=1 AND taken_at >= '2003' "
        "ORDER BY taken_at"
    ).fetchall()
    conn.execute(
        "UPDATE items SET gps_est_lat=NULL, gps_est_lon=NULL, gps_est_conf=NULL, gps_est_place=NULL, gps_est_place_text=''"
    )
    ids, times, lat, lon = [], [], [], []
    for item_id, taken, la, lo in rows:
        try:
            times.append(datetime.fromisoformat(str(taken)[:19]).timestamp() / 60.0)  # minutes
        except ValueError:
            continue
        ids.append(item_id)
        lat.append(np.nan if la is None else la)
        lon.append(np.nan if lo is None else lo)
    ids, times, lat, lon = np.array(ids, np.int64), np.array(times), np.array(lat), np.array(lon)
    has = ~np.isnan(lat)
    report: dict[str, Any] = {"kinds": [], "located": 0, "without_gps": int((~has).sum())}
    if has.sum() < min_samples * 2:
        conn.commit()
        return report
    tg, lg, og = times[has], lat[has], lon[has]
    # 1. test: hide each GPS photo in turn, guess from the GPS photos on either side of it, compare with the truth
    pos = np.arange(len(tg))
    bucket, plat, plon = _guess(tg, tg, lg, og, pos - 1, pos + 1)
    correct = _haversine(plat, plon, lg, og) <= RADIUS_KM
    accepted: dict[int, float] = {}
    for b in range(2 * len(GAP_EDGES_MIN)):
        mask = bucket == b
        n = int(mask.sum())
        precision = float(correct[mask].mean()) if n else 0.0
        ok = n >= min_samples and precision >= min_precision
        label = (
            "neighbours agree, " if b < len(GAP_EDGES_MIN) else "one neighbour, "
        ) + f"within {GAP_EDGES_MIN[b % len(GAP_EDGES_MIN)]} min"
        report["kinds"].append({"kind": label, "tested": n, "accuracy": round(precision, 3), "used": ok})
        if ok:
            accepted[b] = precision
    # 2. apply the kinds that passed to the photos that have no GPS
    q = ~has
    qb, qlat, qlon = _guess(times[q], tg, lg, og, np.searchsorted(tg, times[q]) - 1, np.searchsorted(tg, times[q]))
    updates = []
    for item_id, b, la, lo in zip(ids[q], qb, qlat, qlon, strict=False):
        if int(b) in accepted:
            place = geo.lookup(float(la), float(lo)) if geo is not None else None
            updates.append(
                (
                    float(la),
                    float(lo),
                    accepted[int(b)],
                    place.label if place else None,
                    place.search_text if place else "",
                    int(item_id),
                )
            )
    conn.executemany(
        "UPDATE items SET gps_est_lat=?, gps_est_lon=?, gps_est_conf=?, gps_est_place=?, gps_est_place_text=? WHERE id=?", updates
    )
    conn.commit()
    report["located"] = len(updates)
    return report
