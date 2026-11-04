"""Where do the photos of a place come from? Plain numbers for one place name, read-only (no photo is opened)."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

import numpy as np


def report(conn: sqlite3.Connection, geo: Any, name: str) -> list[str]:
    from ..search.filters import haversine_km
    from ..search.metadata import place_ids

    lines: list[str] = []
    total, with_gps, with_place = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(gps_lat IS NOT NULL),0), COALESCE(SUM(place IS NOT NULL AND place<>''),0) FROM items WHERE missing=0 AND meta_done=1"
    ).fetchone()
    lines.append(f"Whole library: {total:,} photos, {with_gps:,} with GPS ({with_gps / max(total, 1):.0%}), {with_place:,} with a place name.")
    tagged = place_ids(conn, name)
    lines.append(f"Photos whose place name says '{name}': {len(tagged):,}")
    found = geo.find(name) if geo is not None else None
    near_ids = np.zeros(0, np.int64)
    if found is None:
        lines.append(f"'{name}' is not in the offline place list, so 'near {name}' cannot be measured.")
    else:
        rows = conn.execute("SELECT id, gps_lat, gps_lon FROM items WHERE missing=0 AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL").fetchall()
        ids = np.array([r[0] for r in rows], np.int64)
        dist = haversine_km(found[0], found[1], np.array([r[1] for r in rows]), np.array([r[2] for r in rows])) if rows else np.zeros(0)
        for km in (25, 50, 100):
            lines.append(f"Photos with GPS within {km} km of {found[2]}: {int((dist <= km).sum()):,}")
        near_ids = ids[dist <= 25]
    anchors = np.union1d(tagged, near_ids)
    if len(anchors):
        marks = ",".join("?" * min(len(anchors), 900))
        events = [r[0] for r in conn.execute(f"SELECT DISTINCT event_id FROM photo_events WHERE item_id IN ({marks})", anchors[:900].tolist())]
        if events:
            emarks = ",".join("?" * len(events))
            trip = conn.execute(f"SELECT i.id, i.gps_lat, i.place FROM photo_events e JOIN items i ON i.id=e.item_id WHERE e.event_id IN ({emarks})", events).fetchall()
            no_gps = sum(1 for r in trip if r[1] is None)
            lines.append(f"Trip photos around those: {len(trip):,} ({no_gps:,} without GPS, {len(trip) - no_gps:,} with GPS)")
            top = Counter(r[2] for r in trip if r[2]).most_common(6)
            lines.append("Places named on those trips: " + "; ".join(f"{p} ({n:,})" for p, n in top))
    return lines
