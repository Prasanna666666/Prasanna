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
                {"place": place, "start": start, "end": stop, "documents": 0, "photos": p["n"], "source": "photos", "status": _status(start, stop, today)}
            )
    upcoming = sorted((t for t in found if t["status"] != "past"), key=lambda t: t["start"])
    past = sorted((t for t in found if t["status"] == "past"), key=lambda t: t["start"], reverse=True)
    return upcoming + past


def _ticket(doc: dict) -> dict[str, Any]:
    f = doc["facts"]
    return {
        "id": doc["id"],
        "name": doc["name"],
        "kind": doc["kind"],
        "title": f.get("title") or doc["name"],
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
            "title": d["facts"].get("title") or d["name"],
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
