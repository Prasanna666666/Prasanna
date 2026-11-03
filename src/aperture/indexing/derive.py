"""Facts worked out from what was already stored: iPhone capture flags and trips/events. No file is read."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

EVENT_GAP = timedelta(hours=36)  # a pause this long between photos starts a new trip or occasion


def meta_flags(record: dict) -> list[str]:
    """Capture flags found in a stored metadata record (maker notes, XMP, lens name). Case-insensitive, tolerant of tag names."""
    body = dict(record)
    body.pop("file", None)  # the file name must not decide (a file called Screenshot)
    text = json.dumps(body, ensure_ascii=False).lower()
    flags: list[str] = []
    for flag, needles in (("live photo", ("contentidentifier", "livephoto")), ("burst", ("burstuuid", "burstid")),
                          ("screenshot", ("screenshot",)), ("portrait mode", ("portraiteffects", "portrait")),
                          ("hdr", ("hdrgain", "hdrimage", "\"hdr\"")), ("panorama", ("panorama",)), ("night mode", ("nightmode", "night mode"))):
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
        "SELECT id, taken_at, place FROM items WHERE missing=0 AND meta_done=1 AND taken_exif=1 AND taken_at >= '2003' ORDER BY taken_at"
    ).fetchall()
    conn.execute("DELETE FROM photo_events")
    conn.execute("DELETE FROM events")
    groups: list[list[tuple[int, str, str]]] = []
    last = None
    for item_id, taken, place in rows:
        try:
            when = datetime.fromisoformat(str(taken)[:19])
        except ValueError:
            continue
        if last is None or when - last > gap:
            groups.append([])
        groups[-1].append((item_id, str(taken)[:10], place or ""))
        last = when
    for group in groups:
        places = Counter(p for _, _, p in group if p)
        top = places.most_common(1)[0][0] if places else ""
        city, _, country = top.rpartition(", ")
        cursor = conn.execute("INSERT INTO events(start, stop, n, place, country) VALUES (?,?,?,?,?)",
                              (group[0][1], group[-1][1], len(group), city or top, country if city else ""))
        conn.executemany("INSERT INTO photo_events(item_id, event_id) VALUES (?,?)", [(i, cursor.lastrowid) for i, _, _ in group])
    conn.commit()
    return len(groups)
