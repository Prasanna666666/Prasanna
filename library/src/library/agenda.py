"""The personal calendar: every date the documents and mails say will matter, taken only from the facts that were read and checked (no model is asked here, so it costs a
single query). A trip from its tickets and bookings, a bill from its due date, a contract or policy from its end date, a medical follow-up from its report."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

from . import store

DUE_KINDS = ("invoice", "receipt", "tax", "insurance", "contract", "annual_statement", "other")
KEEP_PAST_DAYS = 30  # a bill that came due last month is still worth seeing
MAX_EVENTS = 500


def iso_day(value: Any) -> str:
    text = str(value or "")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _money(facts: dict) -> str:
    total = facts.get("total")
    return f"{facts.get('currency') or ''} {total:,.2f}".strip() if isinstance(total, int | float) else ""


def _event(kind: str, day: str, title: str, subtitle: str = "", end: str = "", doc: int | None = None) -> dict[str, Any]:
    return {"type": kind, "date": day, "end": end or day, "title": title, "subtitle": subtitle, "doc": doc}


def _collect(conn) -> tuple[list[dict[str, Any]], int]:
    """Every dated thing the documents say, with the same fact seen in several places (the mail and its attachment, a reminder and the bill) kept once, what is already settled
    (a receipt carries the bill's reference) left out, and anything half understood left out too: a date without who it is from or what it is for helps nobody.
    Also returns how many were left out as incomplete."""
    found: dict[tuple, dict[str, Any]] = {}
    paid: set[str] = set()
    incomplete = 0
    rows = [(r["id"], r["name"], json.loads(r["facts"])) for r in conn.execute("SELECT id, name, facts FROM documents WHERE judged=1 AND facts<>''")]
    for _id, _name, facts in rows:
        if facts.get("kind") == "receipt" and str(facts.get("reference") or "").strip():
            paid.add(str(facts["reference"]).strip().casefold())

    def keep(key: tuple, e: dict[str, Any]) -> None:
        if key in found:
            found[key]["sources"] += 1
        else:
            found[key] = {**e, "sources": 1}

    for trip in store.trips(conn):
        keep(
            ("trip", trip["start"], trip["place"].casefold()),
            _event("trip", trip["start"], trip["place"], f"{trip['documents']} document{'' if trip['documents'] == 1 else 's'}", trip["end"]),
        )
    for doc_id, name, facts in rows:
        if facts.get("partial"):
            continue  # only the kind and a title were understood: not enough to put a date on a calendar
        title = store.proper_name(facts, name, facts.get("kind", ""))
        kind = facts.get("kind", "other")
        reference = str(facts.get("reference") or "").strip().casefold()
        due = iso_day(facts.get("due_date"))
        if kind in DUE_KINDS and due:
            if not (facts.get("party") or facts.get("total") is not None):
                incomplete += 1  # a due date with no idea who it is for or how much
            elif reference not in paid or not reference:
                who = str(facts.get("party") or "").casefold()
                keep(("due", due, who, reference or title.casefold(), facts.get("total")), _event("due", due, title, _money(facts), doc=doc_id))
        if kind in ("contract", "insurance") and iso_day(facts.get("end_date")):
            keep(
                ("ends", iso_day(facts["end_date"]), title.casefold()), _event("ends", iso_day(facts["end_date"]), title, facts.get("party") or "", doc=doc_id)
            )
        follow = iso_day((facts.get("health") or {}).get("follow_up"))
        if follow:
            keep(("followup", follow, title.casefold()), _event("followup", follow, title, facts.get("party") or "", doc=doc_id))
    return sorted(found.values(), key=lambda e: (e["date"], e["type"], e["title"])), incomplete


def events(conn, since: str, until: str) -> list[dict[str, Any]]:
    """Everything dated between the two days (inclusive), oldest first."""
    everything, _ = _collect(conn)
    return [e for e in everything if since <= e["end"] and e["date"] <= until][:MAX_EVENTS]


def incomplete(conn) -> int:
    """How many dated documents were left out because they are only half understood."""
    return _collect(conn)[1]


def upcoming(conn, today: str, days: int = 60) -> list[dict[str, Any]]:
    """What is coming in the next `days` days, each with how many days away it is, and what came due recently and may still be open."""
    start = (date.fromisoformat(today) - timedelta(days=KEEP_PAST_DAYS)).isoformat()
    end = (date.fromisoformat(today) + timedelta(days=days)).isoformat()
    out = []
    for e in events(conn, start, end):
        away = (date.fromisoformat(e["date"]) - date.fromisoformat(today)).days
        if away < 0 and e["type"] != "due":
            continue  # a trip or follow-up in the past is history, a bill in the past may still be unpaid
        out.append({**e, "days": away})
    return out


def ics(items: list[dict[str, Any]]) -> str:
    """The events as a calendar file to open in Calendar. Offline: nothing is sent anywhere."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Atlas//Calendar//EN", "CALSCALE:GREGORIAN"]
    for e in items:
        uid = hashlib.sha256(f"{e['type']}|{e['date']}|{e['title']}".encode()).hexdigest()[:24]
        first = e["date"].replace("-", "")
        after = (date.fromisoformat(e["end"]) + timedelta(days=1)).strftime("%Y%m%d")
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
