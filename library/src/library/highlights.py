"""One card per app for the Atlas home page: the few things that matter right now, as small facts, never prose. Cheap: counts and one query each, no model."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import casebook, pictures, readreport, store, travel


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _pending_note(conn) -> str:
    """Said on a card while documents are still being understood: what is shown covers only the rest, and will change."""
    counts = store.counts(conn)
    waiting = counts["waiting"] + counts["unclear"]
    return f"{waiting:,} documents are still being understood: this may change." if waiting else ""


def health(conn, state: Any) -> dict[str, Any]:
    values = store.health_values(conn)
    follow = store.health_followups(conn, _today())["follow_ups"]
    flagged = values["attention"]
    total = len(values["tests"])
    items = [{"label": g["test"], "value": f"{g['latest']['value']} {g['unit']}".strip()} for g in flagged[:3]]
    if follow:
        items.append({"label": "Next check", "value": follow[0]["date"]})
    return {
        "headline": "No values yet" if not total else (f"{len(flagged)} to look at" if flagged else "All within range"),
        "sub": f"{total} tests" if total else "",
        "tone": "warn" if flagged else "good",
        "items": items,
        "note": _pending_note(conn),
        "link": "#/health",
    }


def trip(conn, state: Any) -> dict[str, Any]:
    trips = travel.trips(conn, state.engine(), _today())
    coming = [t for t in trips if t["status"] != "past"]
    if not trips:
        return {"headline": "No trips yet", "sub": "", "link": "#/travel"}
    star = (coming or trips)[0]
    n = (date.fromisoformat(star["start"]) - date.fromisoformat(_today())).days
    when = "on now" if star["status"] == "now" else (f"in {n} days" if n > 1 else "tomorrow" if n == 1 else f"{-n} days ago")
    card = {"headline": star["place"], "sub": f"{'Next trip' if coming else 'Last trip'} · {when}", "figure": max(n, 0) if coming else None, "link": "#/travel"}
    if star.get("cover") is not None:
        card["images"] = [star["cover"]]
    return card


def photos(conn, state: Any) -> dict[str, Any]:
    engine = state.engine()
    if engine is None:
        return {"headline": "Not connected", "sub": "the photo drive was not found", "link": "#/photos"}
    counts = pictures.counts(engine)
    ids = pictures.browse(engine, "highlights", {}).get("ids") or pictures.browse(engine, "library", {}).get("ids") or []
    return {"headline": f"{counts['pictures']:,} photos", "sub": "", "images": ids[:6], "link": "#/photos"}


def documents(conn, state: Any) -> dict[str, Any]:
    counts = store.counts(conn)
    not_read = sum(readreport.unread_counts().values())
    items = [{"label": m["title"], "value": m["next"].get("date") or m["status"]} for m in casebook.open_matters(conn)[:3]]
    if counts["waiting"]:
        items.append({"label": "Waiting for the model", "value": f"{counts['waiting']:,}"})
    if counts["unclear"]:
        items.append({"label": "Not understood yet", "value": f"{counts['unclear']:,}"})
    if not_read:
        items.append({"label": "Not read", "value": f"{not_read:,}"})
    return {
        "headline": f"{counts['documents']:,} files and mail",
        "sub": "read and kept as facts",
        "items": items,
        "tone": "warn" if (counts["waiting"] or not_read) else "good",
        "link": "#/",
    }


CARDS = {"health": health, "travel": trip, "photos": photos, "documents": documents}


def card(app: str, conn, state: Any) -> dict[str, Any] | None:
    make = CARDS.get(app)
    return make(conn, state) if make else None
