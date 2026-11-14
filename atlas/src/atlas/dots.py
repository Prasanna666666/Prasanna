"""Joining the dots, kept small: the library has already read each matter as a whole, with every piece found and put together. What is left here is what only Atlas can see:
the bank. A matter whose amount was paid (the same amount, to a payee named in the matter) is settled; a trip shows what was spent while it lasted. Pure functions, nothing guessed."""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any

KEEP_PAST_DAYS = 30
CENT = 0.005


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def tokens(text: str) -> set[str]:
    """The words that can identify a payee or a reference in free text."""
    return set(re.findall(r"[a-z0-9]{4,}", (text or "").casefold()))


def _same_amount(a: Any, b: Any) -> bool:
    return isinstance(a, int | float) and isinstance(b, int | float) and abs(float(a) - float(b)) < CENT


def _names(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Do two items name the same party?"""
    return bool(tokens(a.get("party", "")) & tokens(b.get("party", "") or b.get("text", "")))


def _cost(trip: dict[str, Any], payments: list[dict[str, Any]], now: date) -> float | None:
    start, end = _day(trip.get("date")), _day(trip.get("end"))
    if start is None or end is None or start > now:
        return None
    spent = [float(p["amount"]) for p in payments if p.get("direction") == "expense" and (w := _day(p.get("date"))) and start <= w <= end]
    return round(sum(spent), 2) if spent else None


def _event(kind: str, when: str, title: str, subtitle: str, doc: Any, *, end: str = "", state: str = "") -> dict[str, Any]:
    return {"type": kind, "date": when, "end": end or when, "title": title, "subtitle": subtitle, "doc": doc, "state": state, "sources": 1}


def _num(value: Any) -> float | None:
    """An amount as the matter states it ("1.234,50", "60,50 EUR", 12.5)."""
    m = re.search(r"\d[\d.,]*", str(value))
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _paid(matter: dict[str, Any], payments: list[dict[str, Any]]) -> bool:
    """Was it paid? A bank payment of exactly one of its amounts to a payee the matter names."""
    amounts = [n for a in matter.get("amounts", []) if (n := _num(a.get("value"))) is not None]
    words = tokens(f"{matter.get('title', '')} {matter.get('what', '')}")
    return any(
        p.get("direction") == "expense" and any(_same_amount(p.get("amount"), a) for a in amounts) and words & tokens(str(p.get("text") or ""))
        for p in payments
    )


def _matter_events(it: dict[str, Any], payments: list[dict[str, Any]], now: date, left_out: dict[str, int]) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """A matter read as a whole by the library: what happens next and when, in its own words, unless it is closed or the bank shows it paid."""
    if not it.get("open"):
        left_out["done"] += 1
        return []
    if _paid(it, payments):
        left_out["settled"] += 1
        return []
    if not _day(it.get("due")):
        return []
    sub = " · ".join(x for x in (it.get("next"), it.get("status")) if x)
    state = "overdue" if it["due"] < now.isoformat() else "open"
    return [(("matter", it["id"], it["due"]), _event("due", it["due"], it["title"], sub, it.get("id"), state=state))]


def _trip_events(it: dict[str, Any], payments: list[dict[str, Any]], now: date) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    cost = _cost(it, payments, now)
    note = (
        [f"{it.get('documents', 0)} documents"]
        + ([f"spent {cost:,.2f}"] if cost is not None else [])
        + ([f"{it['photos']} photos"] if it.get("photos") else [])
    )
    return [(("trip", it["date"], str(it["title"]).casefold()), _event("trip", it["date"], it["title"], " · ".join(note), None, end=it.get("end", "")))]


def agenda(items: list[dict[str, Any]], today: str, days: int = 60) -> dict[str, Any]:
    """The events worth showing: each matter's next step and each trip, once, in its true state."""
    docs = [i for i in items if i.get("src") == "documents"]
    payments = [i for i in items if i.get("kind") == "payment"]
    now = _day(today)
    if now is None:
        return {"events": [], "left_out": {}}
    start, stop = now - timedelta(days=KEEP_PAST_DAYS), now + timedelta(days=days)
    found: dict[tuple[Any, ...], dict[str, Any]] = {}
    left_out = {"settled": 0, "done": 0}
    for it in docs:
        made = (
            _matter_events(it, payments, now, left_out) if it.get("kind") == "matter" else _trip_events(it, payments, now) if it.get("kind") == "trip" else []
        )
        for key, e in made:
            when, end = _day(e["date"]), _day(e["end"])
            if when is None or end is None or end < start or when > stop:
                continue
            found.setdefault(key, {**e, "days": (when - now).days, "ended": end < now})
    events = sorted((e for e in found.values() if not (e["ended"] and e["type"] != "due")), key=lambda e: (e["date"], e["type"], e["title"]))
    return {"events": events, "left_out": left_out}


def ics(events: list[dict[str, Any]]) -> str:
    """The joined events as a calendar file to open in Calendar. Offline: nothing is sent anywhere."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Atlas//Calendar//EN", "CALSCALE:GREGORIAN"]
    for e in events:
        uid = hashlib.sha256(f"{e['type']}|{e['date']}|{e['title']}".encode()).hexdigest()[:24]
        first = e["date"].replace("-", "")
        after = ((_day(e["end"]) or _day(e["date"]) or date(2000, 1, 1)) + timedelta(days=1)).strftime("%Y%m%d")
        summary = "".join(c for c in e["title"] if c not in ",;\n\r\\")[:120]
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
