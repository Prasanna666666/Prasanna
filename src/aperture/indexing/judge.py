"""The vision judge: a vision-language model reads EVERYTHING it can from a picture, for the photos the fast methods could not decide.

Slow (seconds per picture) and therefore used only where it is needed: photos with no GPS that were not located by time or by what the
picture looks like. Each picture is analysed once and the full answer is stored for good. A place the judge names is accepted only when
something independent agrees (the places of the photos taken around the same time), or when the judge's place answers were measured
>= 95% accurate on photos whose real place is known (`calibrate`).
"""

from __future__ import annotations

import io
import json
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..config import preview_rel
from ..db import meta_get, meta_set
from .derive import MIN_PRECISION

MODEL_SIDE = 768  # pictures are shrunk before the model sees them: much faster, enough to read a scene
AGREE_KM = 60.0
SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string"},
        "setting": {"type": "string", "enum": ["indoor", "outdoor", "unclear"]},
        "scene": {"type": "string"},
        "objects": {"type": "array", "items": {"type": "string"}},
        "people": {"type": "object", "properties": {"count": {"type": "integer"}, "description": {"type": "string"}}},
        "activity": {"type": "string"},
        "landmarks": {"type": "array", "items": {"type": "string"}},
        "place": {"type": "object", "properties": {"city": {"type": "string"}, "country": {"type": "string"},
                                                   "evidence": {"type": "string"}, "sure": {"type": "boolean"}}},
        "text_visible": {"type": "array", "items": {"type": "string"}},
        "time_of_day": {"type": "string"},
        "season": {"type": "string"},
        "weather": {"type": "string"},
        "dominant_colors": {"type": "array", "items": {"type": "string"}},
        "kind": {"type": "string", "enum": ["photo", "screenshot", "document", "drawing", "other"]},
    },
    "required": ["caption", "scene", "objects", "place"],
}
PROMPT = ("Look closely at this picture and report everything you can see: a one-sentence caption, whether it is indoors or outdoors, the scene, "
          "the objects, how many people and what they look like, what is going on, any landmarks, the words visible anywhere in it, time of day, "
          "season, weather, main colours, and what kind of image it is. For the place, name the city and country only if the picture really shows "
          "it (a famous landmark, a readable sign, unmistakable architecture) and say what tells you; otherwise leave the city empty and set sure to false.")


def shrink(jpeg: bytes) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(jpeg)) as image:
        image = image.convert("RGB")
        image.thumbnail((MODEL_SIDE, MODEL_SIDE))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=85)
        return out.getvalue()


def analyse(vision: Any, jpeg: bytes) -> dict:
    from ..agent.jsonutil import extract_json

    data = extract_json(vision.extract(shrink(jpeg), PROMPT, SCHEMA, 900))
    return data if isinstance(data, dict) else {}


def labels_of(data: dict) -> list[str]:
    """Searchable words from a full analysis."""
    words: list[str] = []
    for key in ("objects", "landmarks"):
        words += [str(w) for w in data.get(key) or []]
    for key in ("scene", "activity", "time_of_day", "season", "weather", "setting", "kind"):
        if data.get(key):
            words.append(str(data[key]))
    return [w.strip().lower() for w in dict.fromkeys(words) if w and len(str(w).strip()) >= 3]


def _time_neighbours(conn: sqlite3.Connection, taken: str, hours: float = 12.0) -> list[tuple[float, float]]:
    try:
        t = datetime.fromisoformat(str(taken)[:19])
    except ValueError:
        return []
    lo, hi = (t.timestamp() - hours * 3600), (t.timestamp() + hours * 3600)
    start, stop = datetime.fromtimestamp(lo).isoformat(sep=" "), datetime.fromtimestamp(hi).isoformat(sep=" ")
    return [(r[0], r[1]) for r in conn.execute("SELECT gps_lat, gps_lon FROM items WHERE missing=0 AND gps_lat IS NOT NULL AND taken_at BETWEEN ? AND ?", (start, stop))]


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from .derive import _haversine

    return float(_haversine(a[0], a[1], b[0], b[1]))


def place_of(data: dict, geo: Any) -> tuple[float, float, str] | None:
    """The coordinates of the city the judge named, if it was sure and the city is on the offline place list."""
    place = data.get("place") or {}
    city = str(place.get("city") or "").strip()
    if not city or place.get("sure") is not True or geo is None:
        return None
    return geo.find(city)


def decide(conn: sqlite3.Connection, taken: str, data: dict, geo: Any) -> tuple[tuple[float, float, str], float] | None:
    """Accept the judge's place only when independent evidence backs it. Returns (place, confidence) or None."""
    found = place_of(data, geo)
    if found is None:
        return None
    near = _time_neighbours(conn, taken)
    if near:
        centre = (float(np.median([p[0] for p in near])), float(np.median([p[1] for p in near])))
        if _km((found[0], found[1]), centre) <= AGREE_KM:
            return found, 0.9  # the judge and the photos taken around that time agree
        return None  # they disagree: the doubt is not resolved, so no location
    measured = float(meta_get(conn, "judge_precision", "0") or 0)
    return (found, measured) if measured >= MIN_PRECISION else None


def pending(conn: sqlite3.Connection, limit: int = 0) -> list[int]:
    """Photos worth the judge's time: no GPS, no estimate, not analysed yet. Photos taken during a trip come first (most likely to resolve)."""
    sql = ("SELECT i.id FROM items i LEFT JOIN photo_vision v ON v.item_id=i.id LEFT JOIN photo_events e ON e.item_id=i.id "
           "WHERE i.missing=0 AND i.meta_done=1 AND i.kind='image' AND i.gps_lat IS NULL AND i.gps_est_lat IS NULL AND v.item_id IS NULL "
           "ORDER BY (e.event_id IS NULL), i.id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r[0] for r in conn.execute(sql)]


def store(conn: sqlite3.Connection, item_id: int, model: str, data: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO photo_vision(item_id, model, data, read_at) VALUES (?,?,?,?)", (item_id, model, json.dumps(data, ensure_ascii=False), time.time()))
    conn.execute("DELETE FROM photo_labels WHERE item_id=? AND source='judge'", (item_id,))
    conn.executemany("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,0.7,'judge')", [(item_id, w) for w in labels_of(data)])


def run(conn: sqlite3.Connection, data_dir: Path, vision: Any, geo: Any, model: str = "vision", seconds: float = 0.0, limit: int = 0,
        stop: Any = None, report: Callable[[int, int, int], None] | None = None) -> dict:
    """Analyse undecided photos until the time budget (seconds, 0 = no limit) or the queue runs out. Resumable; every answer is kept."""
    todo = pending(conn, limit)
    deadline = time.monotonic() + seconds if seconds else None
    done = located = failed = 0
    last_error = ""
    for n, item_id in enumerate(todo, 1):
        if (stop is not None and stop.is_set()) or (deadline is not None and time.monotonic() > deadline):
            break
        try:
            data = analyse(vision, (data_dir / preview_rel(item_id)).read_bytes())
        except Exception as exc:
            failed += 1
            last_error = last_error or f"{type(exc).__name__}: {exc}"[:300]
            continue
        store(conn, item_id, model, data)
        done += 1
        taken = conn.execute("SELECT taken_at FROM items WHERE id=?", (item_id,)).fetchone()[0]
        verdict = decide(conn, taken or "", data, geo)
        if verdict is not None:
            (la, lo, label), conf = verdict
            place = geo.lookup(la, lo) if geo is not None else None
            conn.execute("UPDATE items SET gps_est_lat=?, gps_est_lon=?, gps_est_conf=?, gps_est_place=?, gps_est_place_text=? WHERE id=?",
                         (la, lo, conf, place.label if place else label, place.search_text if place else "", item_id))
            located += 1
        if n % 10 == 0:
            conn.commit()
            if report:
                report(n, len(todo), located)
    conn.commit()
    return {"analysed": done, "located": located, "failed": failed, "left": max(len(todo) - done - failed, 0), "error": last_error}


def calibrate(conn: sqlite3.Connection, data_dir: Path, vision: Any, geo: Any, samples: int = 100, seed: int = 3) -> dict:
    """How right is the judge's place when the real place is known? Run it on photos that do have GPS and compare."""
    rows = conn.execute("SELECT id, gps_lat, gps_lon FROM items WHERE missing=0 AND meta_done=1 AND kind='image' AND gps_lat IS NOT NULL").fetchall()
    rng = np.random.default_rng(seed)
    picks = [rows[i] for i in rng.permutation(len(rows))[:samples]]
    named = right = 0
    for item_id, la, lo in picks:
        try:
            data = analyse(vision, (data_dir / preview_rel(item_id)).read_bytes())
        except Exception:
            continue
        found = place_of(data, geo)
        if found is None:
            continue
        named += 1
        right += _km((found[0], found[1]), (la, lo)) <= AGREE_KM
    precision = right / named if named else 0.0
    meta_set(conn, "judge_precision", f"{precision:.3f}")
    conn.commit()
    return {"tested": len(picks), "named_a_place": named, "right": int(right), "precision": round(precision, 3)}
