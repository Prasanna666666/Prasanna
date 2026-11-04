"""Which sport is this a venue for? The vision model reads only the photos that already look like a sports venue.

The fast labels (stadium, arena, court, rink, field ...) pick a few hundred candidates; the slow vision model then looks at each one ONCE and the
answer is stored for good. After that "hockey stadium in Nagoya" is an instant lookup, not a guess from how a picture looks in general.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import preview_rel
from .judge import shrink

SCHEMA = {
    "type": "object",
    "properties": {
        "sports_venue": {"type": "boolean"},
        "sport": {"type": "string"},
        "venue_type": {"type": "string", "enum": ["stadium", "arena", "field", "court", "rink", "gym", "pool", "track", "other"]},
        "evidence": {"type": "string"},
        "event_in_progress": {"type": "boolean"},
    },
    "required": ["sports_venue", "sport", "venue_type", "evidence"],
}
PROMPT = ("Look closely at this picture. Is it a sports venue (a stadium, arena, field, court, rink, gym, pool or track)? If it is, which sport is it "
          "for? Judge by the markings, goals, nets, hoops, rinks, equipment, scoreboards, signs and uniforms, and say what you saw as evidence. "
          "If you cannot tell the sport from what is visible, write 'unknown' for sport. If it is not a sports venue, set sports_venue to false.")
CANDIDATE_LABELS = ("stadium", "arena", "sport", "athletic", "court", "rink", "gym", "field", "football", "cricket", "tennis", "swimming pool")
NO_SPORT = {"", "unknown", "none", "n/a", "unclear", "not applicable"}
LABEL_SCORE = 0.8


def _parse(raw: str) -> dict:
    """The model's JSON, tolerating a little text around it."""
    from ..agent.jsonutil import extract_json

    data = extract_json(raw)
    return data if isinstance(data, dict) else {}


def candidates(conn: sqlite3.Connection, limit: int = 0) -> list[int]:
    """Photos that look like a sports venue by the fast labels and have not been looked at yet, most likely first."""
    marks = " OR ".join("l.label LIKE ?" for _ in CANDIDATE_LABELS)
    sql = (f"SELECT l.item_id, MAX(l.score) FROM photo_labels l LEFT JOIN photo_venues v ON v.item_id=l.item_id "
           f"WHERE v.item_id IS NULL AND l.score >= 0.5 AND l.source <> 'venue' AND ({marks}) GROUP BY l.item_id ORDER BY 2 DESC, 1")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r[0] for r in conn.execute(sql, [f"%{w}%" for w in CANDIDATE_LABELS])]


def labels_of(data: dict) -> list[str]:
    """Searchable labels from one analysis: only when it says it is a sports venue and gives evidence."""
    if data.get("sports_venue") is not True or not str(data.get("evidence") or "").strip():
        return []
    sport = str(data.get("sport") or "").strip().lower()
    venue = str(data.get("venue_type") or "").strip().lower()
    out = ["sports venue"]
    if venue and venue != "other":
        out.append(venue)
    if sport not in NO_SPORT:
        out.append(sport)
        if venue and venue != "other":
            out.append(f"{sport} {venue}")
    return list(dict.fromkeys(out))


def store(conn: sqlite3.Connection, item_id: int, data: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO photo_venues(item_id, data, read_at) VALUES (?,?,?)", (item_id, json.dumps(data, ensure_ascii=False), time.time()))
    conn.execute("DELETE FROM photo_labels WHERE item_id=? AND source='venue'", (item_id,))
    conn.executemany("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,?,'venue')", [(item_id, w, LABEL_SCORE) for w in labels_of(data)])


def run(conn: sqlite3.Connection, data_dir: Path, vision: Any, seconds: float = 0.0, limit: int = 0, stop: Any = None,
        report: Callable[[int, int], None] | None = None) -> dict:
    """Look at the candidates until the time budget (0 = no limit) or the list runs out. Resumable; every answer is kept."""
    todo = candidates(conn, limit)
    deadline = time.monotonic() + seconds if seconds else None
    done = failed = venues = 0
    last_error = ""
    for n, item_id in enumerate(todo, 1):
        if (stop is not None and stop.is_set()) or (deadline is not None and time.monotonic() > deadline):
            break
        try:
            raw = vision.extract(shrink((data_dir / preview_rel(item_id)).read_bytes()), PROMPT, SCHEMA, 500)
            data = _parse(raw)
        except Exception as exc:  # the first reason is kept and shown: a silent failure cannot be fixed
            failed += 1
            last_error = last_error or f"{type(exc).__name__}: {exc}"[:300]
            continue
        store(conn, item_id, data)
        done += 1
        venues += bool(labels_of(data))
        if n % 10 == 0:
            conn.commit()
            if report:
                report(n, len(todo))
    conn.commit()
    return {"looked_at": done, "sports_venues": venues, "failed": failed, "left": max(len(todo) - done - failed, 0), "error": last_error}
