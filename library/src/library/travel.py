"""Travel: trips from the tickets and bookings that were read (and from photos taken on journeys), each with its documents, its booked amounts and its photos.

Everything is read from the documents and the photo index: dates and places only as the documents write them, amounts only when verified against the document's
text. What a trip cost in total is the Finance app's business: the trip page asks the assistant, which adds up the real payments."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

from . import pictures, store

PHOTO_TRIP_MIN = 5  # a run of photos with a place counts as a trip only from this many


def _status(start: str, end: str, today: str) -> str:
    return "upcoming" if start > today else "past" if end < today else "now"


def _overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return a_start <= b_end and b_start <= a_end


def trips(conn, engine, today: str) -> list[dict[str, Any]]:
    """Every trip, soonest first: those from tickets and bookings, plus photo trips that no ticket explains. Each says where it came from."""
    found = [{**t, "source": "documents", "status": _status(t["start"], t["end"], today)} for t in store.trips(conn)]
    if engine is not None:
        for p in pictures.browse(engine, "trips", {}):
            place, start, stop = p.get("place") or "", p["start"], p["stop"]
            if not place or p["n"] < PHOTO_TRIP_MIN or any(_overlaps(start, stop, t["start"], t["end"]) for t in found):
                continue
            found.append(
                {
                    "place": place,
                    "start": start,
                    "end": stop,
                    "documents": 0,
                    "photos": p["n"],
                    "source": "photos",
                    "status": _status(start, stop, today),
                    "cover": p.get("cover"),
                }
            )
        for t in found:  # a picture from those days to show the trip by
            if t.get("cover") is None and t["start"] <= today:
                ids = pictures.browse(engine, "library", {"from": t["start"], "to": t["end"]}).get("ids") or []
                t["cover"] = ids[0] if ids else None
    upcoming = sorted((t for t in found if t["status"] != "past"), key=lambda t: t["start"])
    past = sorted((t for t in found if t["status"] == "past"), key=lambda t: t["start"], reverse=True)
    return upcoming + past


def _ticket(doc: dict) -> dict[str, Any]:
    f = doc["facts"]
    return {
        "id": doc["id"],
        "name": doc["name"],
        "kind": doc["kind"],
        "title": doc["title"],
        "party": f.get("party") or "",
        "start_date": f.get("start_date") or "",
        "end_date": f.get("end_date") or "",
        "reference": f.get("reference") or "",
        "total": f.get("total"),
        "currency": f.get("currency") or "",
    }


def detail(conn, engine, place: str, start: str, end: str) -> dict[str, Any]:
    """One trip: its tickets and bookings, other documents dated in those days, the amounts the tickets and bookings print (added up per currency, exactly), and photos."""
    window_start = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    window_end = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    booked = [
        _ticket(d)
        for d in store.list_documents(conn, ["ticket", "booking"], limit=500)
        if place.casefold() in str(d["facts"].get("place") or "").casefold()
        and _overlaps(str(d["facts"].get("start_date") or "9"), str(d["facts"].get("end_date") or d["facts"].get("start_date") or "0"), start, end)
    ]
    booked_ids = {t["id"] for t in booked}
    others = [
        {
            "id": d["id"],
            "name": d["name"],
            "kind": d["kind"],
            "title": d["title"],
            "date": str(d["facts"].get("date") or d["facts"].get("start_date") or ""),
        }
        for d in store.documents_between(conn, window_start, window_end, limit=60)
        if d["id"] not in booked_ids and d["kind"] not in ("ticket", "booking")
    ]
    minor: dict[str, int] = {}
    for t in booked:
        if t["total"] is not None:
            minor[t["currency"] or "?"] = minor.get(t["currency"] or "?", 0) + round(t["total"] * 100)
    photos: dict[str, Any] = {"total": 0, "ids": []}
    if engine is not None:
        page = pictures.browse(engine, "library", {"from": start, "to": end})
        photos = {"total": page["total"], "ids": page["ids"][:24]}
    return {
        "place": place,
        "start": start,
        "end": end,
        "tickets": sorted(booked, key=lambda t: (t["start_date"], t["id"])),
        "other_documents": others,
        "booked_totals": {c: v / 100 for c, v in sorted(minor.items())},
        "photos": photos,
    }


def calendar(trip_list: list[dict[str, Any]]) -> str:
    """The trips as an .ics file (whole days, the end day included), to open in Calendar. Offline, nothing is sent anywhere."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Atlas//Travel//EN", "CALSCALE:GREGORIAN"]
    for t in trip_list:
        uid = hashlib.sha256(f"{t['place']}|{t['start']}|{t['end']}".encode()).hexdigest()[:24]
        first = t["start"].replace("-", "")
        after = (date.fromisoformat(t["end"]) + timedelta(days=1)).strftime("%Y%m%d")
        summary = "".join(c for c in f"Trip: {t['place']}" if c not in ",;\n\r\\")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@atlas",
            f"DTSTAMP:{first}T000000Z",
            f"DTSTART;VALUE=DATE:{first}",
            f"DTEND;VALUE=DATE:{after}",
            f"SUMMARY:{summary}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ---- the packing list of a trip: the person's own checklist, started from a standard list whose quantities follow from the number of days --------------------
MAX_ITEMS = 200
SECTIONS = ("Documents", "Money", "Clothes", "Toiletries", "Health", "Electronics", "Other")


def trip_key(place: str, start: str) -> str:
    return hashlib.sha256(f"{place.casefold()}|{start}".encode()).hexdigest()[:16]


def starter_items(days: int) -> list[tuple[str, str]]:
    """A standard packing list as (section, item). Quantities are plain arithmetic on the number of days: tops one a day (at most 7), underwear and socks a day
    and one more (at most 8), trousers or skirts one for every three days and one more (at most 4); on a longer trip you wash."""
    days = max(1, days)
    return [
        ("Documents", "Passport or ID"),
        ("Documents", "Tickets and boarding passes"),
        ("Documents", "Hotel and other bookings"),
        ("Documents", "Travel insurance"),
        ("Documents", "Driving licence"),
        ("Money", "Bank cards"),
        ("Money", "Some cash"),
        ("Clothes", f"Tops: {min(days, 7)}"),
        ("Clothes", f"Underwear and socks: {min(days + 1, 8)}"),
        ("Clothes", f"Trousers or skirts: {min(-(-days // 3) + 1, 4)}"),
        ("Clothes", "A warm layer"),
        ("Clothes", "A rain jacket"),
        ("Clothes", "Comfortable shoes"),
        ("Clothes", "Sleepwear"),
        ("Toiletries", "Toothbrush and toothpaste"),
        ("Toiletries", "Deodorant and soap"),
        ("Toiletries", "Sunscreen"),
        ("Health", "Your regular medicines"),
        ("Health", "Basic first-aid items"),
        ("Electronics", "Phone and charger"),
        ("Electronics", "Power bank"),
        ("Electronics", "Plug adapter, if the country needs one"),
        ("Electronics", "Headphones"),
    ]


def packing(conn, place: str, start: str) -> dict[str, Any]:
    """The checklist of one trip, by section, with how many items are packed."""
    key = trip_key(place, start)
    items = [dict(r) for r in conn.execute("SELECT id, section, text, done FROM trip_items WHERE trip=? ORDER BY pos, id", (key,))]
    order = {name: i for i, name in enumerate(SECTIONS)}
    items.sort(key=lambda x: (order.get(x["section"], len(SECTIONS)), x["id"]))
    return {"key": key, "items": items, "packed": sum(1 for x in items if x["done"]), "total": len(items)}


def packing_action(conn, body: dict[str, Any]) -> dict[str, Any]:
    """add / toggle / delete one item, or start the standard list. Only this checklist changes; it is the person's own list, nothing in their files."""
    place, start, end = str(body.get("place", ""))[:80], str(body.get("start", ""))[:10], str(body.get("end", ""))[:10]
    try:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    except ValueError as why:
        raise ValueError("a trip needs a start and an end day") from why
    key, action = trip_key(place, start), body.get("action")
    count = conn.execute("SELECT COUNT(*) FROM trip_items WHERE trip=?", (key,)).fetchone()[0]
    if action == "seed":
        if count:
            raise ValueError("this trip already has a list")
        conn.executemany(
            "INSERT INTO trip_items (trip, section, text, pos) VALUES (?,?,?,?)", [(key, sec, text, i) for i, (sec, text) in enumerate(starter_items(days))]
        )
    elif action == "add":
        text = " ".join(str(body.get("text", "")).split())[:120]
        section = str(body.get("section", "")) if str(body.get("section", "")) in SECTIONS else "Other"
        if not text:
            raise ValueError("write what to pack")
        if count >= MAX_ITEMS:
            raise ValueError(f"a list holds at most {MAX_ITEMS} items")
        conn.execute("INSERT INTO trip_items (trip, section, text, pos) VALUES (?,?,?,?)", (key, section, text, count))
    elif action in ("toggle", "delete"):
        item = int(body.get("id", 0))
        if action == "toggle":
            conn.execute("UPDATE trip_items SET done=1-done WHERE id=? AND trip=?", (item, key))
        else:
            conn.execute("DELETE FROM trip_items WHERE id=? AND trip=?", (item, key))
    else:
        raise ValueError("unknown action")
    conn.commit()
    return {"ok": True, **packing(conn, place, start)}
