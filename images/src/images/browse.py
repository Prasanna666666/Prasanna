"""Browsing the library like a website: every photo by date, trips, places and people. Read-only, exact counts, and nothing leaves this Mac."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from .albums import build_albums

PAGE = 60
LIVE = "i.missing=0 AND i.meta_done=1 AND i.kind='image'"  # the photos that can be shown
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH = re.compile(r"^\d{4}-\d{2}$")
_YEAR = re.compile(r"^\d{4}$")


def library(conn: sqlite3.Connection, q: dict[str, str], offset: int = 0, limit: int = PAGE) -> dict[str, Any]:
    """Photos newest first, a page at a time, narrowed by year, month, a date range, a place or a person. `total` counts the whole selection."""
    where: list[str] = [LIVE]
    args: list[Any] = []
    if _YEAR.match(q.get("year", "")):
        where.append("substr(i.taken_at,1,4)=?")
        args.append(q["year"])
    if _MONTH.match(q.get("month", "")):
        where.append("substr(i.taken_at,1,7)=?")
        args.append(q["month"])
    if _DAY.match(q.get("from", "")):
        where.append("substr(i.taken_at,1,10)>=?")
        args.append(q["from"])
    if _DAY.match(q.get("to", "")):
        where.append("substr(i.taken_at,1,10)<=?")
        args.append(q["to"])
    if q.get("place"):
        where.append("i.place=?")
        args.append(q["place"][:200])
    if q.get("person", "").isdigit():
        where.append("i.id IN (SELECT item_id FROM faces WHERE person_id=?)")
        args.append(int(q["person"]))
    clause = " WHERE " + " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM items i{clause}", args).fetchone()[0]
    limit, offset = max(1, min(int(limit), 200)), max(0, int(offset))
    ids = [
        r[0]
        for r in conn.execute(
            f"SELECT i.id FROM items i{clause} ORDER BY i.taken_at DESC, i.id DESC LIMIT ? OFFSET ?", [*args, limit, offset]
        )
    ]
    return {"total": total, "ids": ids, "offset": offset, "more": offset + len(ids) < total}


HIGHLIGHT_MIN_PIXELS = 2_000_000  # small pictures (icons, thumbnails) are never highlights
HIGHLIGHT_MAX_TEXT = 40  # a picture full of text is a screenshot, a receipt or a letter, not a memory
HIGHLIGHT_GAP_SECONDS = 120  # two pictures this close are the same moment: only the better one is shown
HIGHLIGHT_PER_DAY = 2
HIGHLIGHT_PER_PLACE = 3


def _score(r: sqlite3.Row) -> float:
    """How good a picture looks, from what was measured: resolution, detail (bytes per pixel: a blurred or flat picture compresses small), people and a place."""
    pixels = r["width"] * r["height"]
    detail = min((r["size"] / pixels) / 1.0, 1.0)
    faces = r["faces"]
    return (
        0.35 * min(pixels / 12_000_000, 1.0)
        + 0.35 * detail
        + (0.25 if 1 <= faces <= 4 else 0.1 if faces else 0.0)
        + (0.1 if r["place"] else 0.0)
    )


def highlights(conn: sqlite3.Connection, limit: int = 12) -> dict[str, Any]:
    """A few of the best pictures, spread over days and places, never the same moment twice and never a screenshot or a document."""
    rows = conn.execute(
        "SELECT i.id, i.width, i.height, i.size, i.taken_at, i.place, "
        f"(SELECT COUNT(*) FROM faces f WHERE f.item_id=i.id) AS faces FROM items i WHERE {LIVE} AND i.width*i.height>=? AND i.ocr_chars<? AND i.thumb IS NOT NULL",
        (HIGHLIGHT_MIN_PIXELS, HIGHLIGHT_MAX_TEXT),
    ).fetchall()
    picked: list[int] = []
    per_day: dict[str, int] = {}
    per_place: dict[str, int] = {}
    taken: list[tuple[str, str]] = []
    for r in sorted(rows, key=lambda r: (-_score(r), -r["id"])):
        if len(picked) >= max(1, min(int(limit), 60)):
            break
        day, at, place = (r["taken_at"] or "")[:10], r["taken_at"] or "", r["place"] or ""
        if day and per_day.get(day, 0) >= HIGHLIGHT_PER_DAY:
            continue
        if place and per_place.get(place, 0) >= HIGHLIGHT_PER_PLACE:
            continue
        if at and any(d == day and abs(_seconds(t) - _seconds(at)) < HIGHLIGHT_GAP_SECONDS for d, t in taken):
            continue
        picked.append(r["id"])
        per_day[day] = per_day.get(day, 0) + 1
        per_place[place] = per_place.get(place, 0) + 1
        taken.append((day, at))
    return {"ids": picked, "total": len(rows)}


def _seconds(stamp: str) -> int:
    """Seconds into the day of 'YYYY-MM-DD HH:MM:SS' (0 when it has no time)."""
    try:
        h, m, s = stamp[11:19].split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except ValueError:
        return 0


def timeline(conn: sqlite3.Connection) -> dict[str, Any]:
    """How many photos each year and month holds, newest first, and how many have no date."""
    years: dict[str, dict[str, Any]] = {}
    for r in conn.execute(
        f"SELECT substr(i.taken_at,1,7) AS m, COUNT(*) AS n FROM items i WHERE {LIVE} AND i.taken_at IS NOT NULL GROUP BY m ORDER BY m DESC"
    ):
        if not r["m"] or not _MONTH.match(r["m"]):
            continue
        y = years.setdefault(r["m"][:4], {"year": r["m"][:4], "total": 0, "months": []})
        y["total"] += r["n"]
        y["months"].append({"month": r["m"], "n": r["n"]})
    undated = conn.execute(f"SELECT COUNT(*) FROM items i WHERE {LIVE} AND i.taken_at IS NULL").fetchone()[0]
    everything = conn.execute(f"SELECT COUNT(*) FROM items i WHERE {LIVE}").fetchone()[0]
    return {"total": everything, "undated": undated, "years": list(years.values())}


def trips(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Trips and occasions, newest first: where, when, how many photos and one to show. From the library's own events, or from runs of photos taken close together."""
    out: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT e.id, e.start, e.stop, e.n, e.place, e.country, (SELECT MIN(pe.item_id) FROM photo_events pe JOIN items i ON i.id=pe.item_id "
        f"WHERE pe.event_id=e.id AND {LIVE}) AS cover FROM events e WHERE e.n>0 ORDER BY e.start DESC LIMIT ?",
        (limit,),
    ).fetchall()
    for r in rows:
        if r["cover"] is not None:
            out.append(
                {
                    "title": r["place"] or r["country"] or "Trip",
                    "place": r["place"],
                    "start": r["start"][:10],
                    "stop": r["stop"][:10],
                    "n": r["n"],
                    "cover": r["cover"],
                }
            )
    if out:
        return out
    for a in build_albums(conn)[:limit]:
        out.append(
            {
                "title": a.place or "Photos",
                "place": a.place,
                "start": a.start,
                "stop": a.end,
                "n": len(a),
                "cover": int(a.ids[len(a.ids) // 2]),
            }
        )
    return out


def places(conn: sqlite3.Connection, limit: int = 150) -> list[dict[str, Any]]:
    """Every place with how many photos were taken there and the latest one as its picture, busiest first."""
    return [
        {
            "place": r["place"],
            "country": r["place"].rsplit(",", 1)[-1].strip() if "," in r["place"] else "",
            "n": r["n"],
            "cover": r["cover"],
        }
        for r in conn.execute(
            f"SELECT i.place AS place, COUNT(*) AS n, MAX(i.id) AS cover FROM items i WHERE {LIVE} AND i.place IS NOT NULL AND i.place<>'' GROUP BY i.place ORDER BY n DESC, i.place LIMIT ?",
            (limit,),
        )
    ]


def people(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """The people found in the photos, most photographed first, each with their clearest face (its photo and where the face sits in it)."""
    out = []
    for p in conn.execute("SELECT id, name FROM people WHERE hidden=0"):
        faces = conn.execute(
            f"SELECT f.item_id, f.x1, f.y1, f.x2, f.y2, f.score FROM faces f JOIN items i ON i.id=f.item_id WHERE f.person_id=? AND {LIVE} ORDER BY f.score DESC",
            (p["id"],),
        ).fetchall()
        if not faces:
            continue
        best = faces[0]
        out.append(
            {
                "id": p["id"],
                "name": (p["name"] or "").strip(),
                "n": len({f["item_id"] for f in faces}),
                "cover": best["item_id"],
                "box": [best["x1"], best["y1"], best["x2"], best["y2"]],
            }
        )
    return sorted(out, key=lambda x: (-x["n"], x["id"]))


def search_links(
    places_: list[dict[str, Any]], people_: list[dict[str, Any]], trips_: list[dict[str, Any]], query: str, limit: int = 12
) -> list[dict[str, str]]:
    """What matches a typed word among places, named people and trips, each with the address inside Photos that opens it (for Atlas, the shared search)."""
    from urllib.parse import quote

    q = query.strip().lower()
    if len(q) < 2:
        return []
    out: list[dict[str, str]] = [
        {"title": p["place"], "subtitle": f"{p['n']:,} photos", "kind": "place", "link": "#/library?place=" + quote(p["place"])}
        for p in places_
        if q in p["place"].lower()
    ]
    out += [
        {"title": p["name"], "subtitle": f"{p['n']:,} photos", "kind": "person", "link": f"#/library?person={p['id']}"}
        for p in people_
        if p["name"] and q in p["name"].lower()
    ]
    out += [
        {
            "title": t["title"],
            "subtitle": f"{t['start']} to {t['stop']} · {t['n']:,} photos",
            "kind": "trip",
            "link": f"#/library?from={t['start']}&to={t['stop']}",
        }
        for t in trips_
        if q in (t["title"] or "").lower() or q in (t["place"] or "").lower()
    ]
    return out[:limit]
