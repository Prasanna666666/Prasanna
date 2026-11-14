"""Joining the dots: the same thing seen by different parts (a bill in a mail and in its attachment, the payment in the bank, the receipt; a follow-up and the report that
followed it; a policy and its renewal; a trip and what it cost) is one thing with one state. Every part hands over plain dated items; this turns them into the events worth
showing, each in its true state, and leaves out what is settled, done or superseded. Pure functions: no network, no model, nothing guessed: a link needs a shared reference, or
the same payee and the same amount inside days that make sense.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any

BILL_KINDS = ("invoice", "tax", "insurance", "contract", "annual_statement", "other")
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


def _settled(bill: dict[str, Any], docs: list[dict[str, Any]], payments: list[dict[str, Any]]) -> str:
    """The day a bill was settled, if a receipt or a payment shows it: the same reference, or the same payee and the same amount, inside the days that make sense."""
    ref = str(bill.get("reference") or "").strip().casefold()
    due, issued = _day(bill.get("due")), _day(bill.get("date"))
    if due is None:
        return ""
    for other in docs:
        if other is bill or other.get("kind") != "receipt":
            continue
        if (ref and str(other.get("reference") or "").strip().casefold() == ref) or (
            _names(bill, other) and _same_amount(bill.get("amount"), other.get("amount"))
        ):
            return str(other.get("date") or "settled")
    start, end = (issued or due - timedelta(days=45)), due + timedelta(days=30)
    for pay in payments:
        when = _day(pay.get("date"))
        if pay.get("direction") != "expense" or when is None or not (start <= when <= end) or not _same_amount(pay.get("amount"), bill.get("amount")):
            continue
        text = str(pay.get("text") or "")
        if (ref and ref in text.casefold()) or tokens(bill.get("party", "")) & tokens(text):
            return str(pay["date"])
    return ""


def _followed_up(item: dict[str, Any], docs: list[dict[str, Any]]) -> bool:
    """A follow-up is done when a newer medical report dated around it exists."""
    follow, anchor = _day(item.get("followup")), _day(item.get("date"))
    for other in docs:
        when = _day(other.get("date"))
        if other is item or other.get("kind") != "medical" or when is None or follow is None:
            continue
        if (anchor is None or when > anchor) and follow - timedelta(days=21) <= when <= follow + timedelta(days=45):
            return True
    return False


def _renewed(item: dict[str, Any], docs: list[dict[str, Any]]) -> bool:
    """A contract or policy that ends is renewed when a newer one from the same party exists."""
    anchor, end = _day(item.get("date")), _day(item.get("end"))
    for other in docs:
        if other is item or other.get("kind") not in ("contract", "insurance") or not _names(item, other):
            continue
        newer, other_end = _day(other.get("date")), _day(other.get("end"))
        if anchor and newer and newer > anchor and (other_end is None or (end is not None and other_end > end)):
            return True
    return False


def _cost(trip: dict[str, Any], payments: list[dict[str, Any]], now: date) -> float | None:
    start, end = _day(trip.get("date")), _day(trip.get("end"))
    if start is None or end is None or start > now:
        return None
    spent = [float(p["amount"]) for p in payments if p.get("direction") == "expense" and (w := _day(p.get("date"))) and start <= w <= end]
    return round(sum(spent), 2) if spent else None


def _event(kind: str, when: str, title: str, subtitle: str, doc: Any, *, end: str = "", state: str = "") -> dict[str, Any]:
    return {"type": kind, "date": when, "end": end or when, "title": title, "subtitle": subtitle, "doc": doc, "state": state, "sources": 1}


def _matter_events(it: dict[str, Any], now: date, left_out: dict[str, int]) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """A matter read as a whole by the library: what happens next and when, in its own words; nothing here knows what sort of matter it is."""
    if not it.get("open"):
        left_out["done"] += 1
        return []
    if not _day(it.get("due")):
        return []
    sub = " · ".join(x for x in (it.get("next"), it.get("status")) if x)
    state = "overdue" if it["due"] < now.isoformat() else "open"
    return [(("matter", it["id"], it["due"]), _event("due", it["due"], it["title"], sub, it.get("id"), state=state))]


def _item_events(
    it: dict[str, Any], docs: list[dict[str, Any]], payments: list[dict[str, Any]], now: date, left_out: dict[str, int]
) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """The events one item gives rise to (a trip, a bill, an ending, a follow-up), each with its key, in its true state; what is settled, done or superseded is counted, not returned."""
    kind = it.get("kind")
    out: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    if kind == "matter":
        return _matter_events(it, now, left_out)
    if kind == "trip":
        cost = _cost(it, payments, now)
        note = (
            [f"{it.get('documents', 0)} documents"]
            + ([f"spent {cost:,.2f}"] if cost is not None else [])
            + ([f"{it['photos']} photos"] if it.get("photos") else [])
        )
        return [(("trip", it["date"], str(it["title"]).casefold()), _event("trip", it["date"], it["title"], " · ".join(note), None, end=it.get("end", "")))]
    if kind in BILL_KINDS and _day(it.get("due")):
        if not (it.get("party") or it.get("amount") is not None or it.get("absent")):
            left_out["incomplete"] += 1
        elif _settled(it, docs, payments):
            left_out["settled"] += 1
        else:
            amount = f"{it.get('currency', '')} {it['amount']:,.2f}".strip() if isinstance(it.get("amount"), int | float) else ""
            key = ("due", it["due"], str(it.get("party", "")).casefold(), str(it.get("reference") or it["title"]).casefold(), it.get("amount"))
            out.append((key, _event("due", it["due"], it["title"], amount, it.get("id"), state="overdue" if it["due"] < now.isoformat() else "open")))
    if kind in ("contract", "insurance") and _day(it.get("end")):
        if _renewed(it, docs):
            left_out["renewed"] += 1
        else:
            out.append((("ends", it["end"], it["title"].casefold()), _event("ends", it["end"], it["title"], it.get("party", ""), it.get("id"))))
    if _day(it.get("followup")):
        if _followed_up(it, docs):
            left_out["done"] += 1
        else:
            out.append(
                (("followup", it["followup"], it["title"].casefold()), _event("followup", it["followup"], it["title"], it.get("party", ""), it.get("id")))
            )
    return out


def agenda(items: list[dict[str, Any]], today: str, days: int = 60) -> dict[str, Any]:
    """The events worth showing, joined across sources: each once, in its true state, and how many items were left out as settled, done or superseded."""
    docs = [i for i in items if i.get("src") == "documents"]
    payments = [i for i in items if i.get("kind") == "payment"]
    now = _day(today)
    if now is None:
        return {"events": [], "left_out": {}}
    start, stop = now - timedelta(days=KEEP_PAST_DAYS), now + timedelta(days=days)
    found: dict[tuple[Any, ...], dict[str, Any]] = {}
    left_out = {"settled": 0, "done": 0, "renewed": 0, "incomplete": 0}
    for it in docs:
        for key, e in _item_events(it, docs, payments, now, left_out):
            when, end = _day(e["date"]), _day(e["end"])
            if when is None or end is None or end < start or when > stop:
                continue
            if key in found:
                found[key]["sources"] += 1
            else:
                found[key] = {**e, "days": (when - now).days, "ended": end < now}
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
