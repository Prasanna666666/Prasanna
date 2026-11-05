"""Browsing the library like a website: every photo by date, trips, places and people. Read-only, exact counts, and nothing leaves this Mac."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from ..albums import build_albums

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
