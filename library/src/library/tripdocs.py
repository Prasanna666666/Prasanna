"""Trips: the documents that are tickets or bookings, grouped into journeys."""

from __future__ import annotations

from datetime import date

from . import apps, store


def trip_documents(conn, limit: int = 500) -> list[dict]:
    """The files that are about a trip: those marked for an app that reads trips (`apps.json`)."""
    found: list[dict] = []
    for name in apps.with_reading("trip"):
        found += store.list_documents(conn, limit=limit, narrow=store.Narrow(app=name))
    return found


def is_trip_document(doc: dict) -> bool:
    return bool(set(doc["apps"]) & set(apps.with_reading("trip")))


# ---- trips: derived from the tickets and bookings that were read -----------------------------------------------------------------
def trips(conn, place: str = "", year: str = "") -> list[dict]:
    """Journeys found in the tickets and bookings: where, from which day to which day (as the documents themselves write them), and how many
    documents show it. Documents for the same place whose dates are within 60 days of each other are one trip. Most documents first."""
    found: dict[str, list[dict]] = {}
    for doc in trip_documents(conn):
        facts = doc["facts"]
        start, name = str(facts.get("start_date") or ""), str(facts.get("place") or "").strip()
        if not start or not name:
            continue
        if place and place.lower() not in name.lower():
            continue
        found.setdefault(name.casefold(), []).append({"place": name, "start": start, "end": str(facts.get("end_date") or start)})
    out: list[dict] = []
    for group in found.values():
        group.sort(key=lambda d: d["start"])
        current: list[dict] = []
        for d in group:
            if current and (date.fromisoformat(d["start"]) - date.fromisoformat(max(c["end"] for c in current))).days > TRIP_GAP_DAYS:
                out.append(_trip(current))
                current = []
            current.append(d)
        out.append(_trip(current))
    if year:
        out = [t for t in out if t["start"].startswith(year) or t["end"].startswith(year)]
    return sorted(out, key=lambda t: (-t["documents"], t["start"]))


TRIP_GAP_DAYS = 60


def _trip(docs: list[dict]) -> dict:
    return {"place": docs[0]["place"], "start": min(d["start"] for d in docs), "end": max(d["end"] for d in docs), "documents": len(docs)}


def documents_of_the_same_matter(conn, ids: list[int], limit: int = 60) -> list[dict]:
    """The documents that grouping put together with these ones (the same matter): a hotel invoice with the booking it belongs to. Not those that merely have a date nearby."""
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT {store.LIST_COLUMNS} FROM documents WHERE case_id IN (SELECT case_id FROM documents WHERE id IN ({marks}) AND case_id IS NOT NULL) AND id NOT IN ({marks}) AND kind<>'email' ORDER BY ready LIMIT ?",
        (*ids, *ids, limit),
    )
    return [store._as_document(r) for r in rows]


def documents_between(conn, start: str, end: str, limit: int = 100) -> list[dict]:
    """Every recognised document dated within the window (its own date, or the dates of a ticket or booking), oldest first."""
    out: list[dict] = []
    for doc in store.list_documents(conn, limit=500, narrow=store.Narrow(source="documents")):  # documents, never a whole email
        facts = doc["facts"]
        day = str(facts.get("start_date") or facts.get("date") or "")
        if day and start <= day <= end:
            out.append(doc)
        if len(out) >= limit:
            break
    return sorted(out, key=lambda d: str(d["facts"].get("start_date") or d["facts"].get("date")))
