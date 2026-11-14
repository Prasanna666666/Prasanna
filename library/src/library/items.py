"""What the documents and mails say, as plain dated items (who, what, when, how much, which reference), for Atlas to join with what other parts know. Facts only, checked ones:
a reading that is only partial is not given out."""

from __future__ import annotations

import json
from typing import Any

from . import store, travel

MAX_ITEMS = 3000


def _amount(facts: dict) -> float | None:
    total = facts.get("total")
    return float(total) if isinstance(total, int | float) else None


def _matters(conn) -> list[dict[str, Any]]:
    """Each matter read as a whole: what it is, its status, the next step, the amounts. Every claim carries the quote it came from."""
    out = []
    for r in conn.execute("SELECT id, members, summary FROM cases WHERE summary<>''"):
        s = json.loads(r["summary"])
        nxt = s.get("next") or {}
        out.append(
            {
                "src": "documents",
                "kind": "matter",
                "id": r["id"],
                "title": s.get("title", ""),
                "what": s.get("what", ""),
                "status": s.get("status", ""),
                "open": bool(s.get("open")),
                "due": nxt.get("date", ""),
                "next": nxt.get("what", ""),
                "dates": s.get("dates", []),
                "amounts": s.get("amounts", []),
                "pieces": len(json.loads(r["members"])),
            }
        )
    return out


def items(conn, state: Any, today: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in conn.execute("SELECT id, name, area, facts, case_id FROM documents WHERE judged=1 AND facts<>'' ORDER BY ready DESC LIMIT ?", (MAX_ITEMS,)):
        facts = json.loads(r["facts"])
        if r["case_id"] is None:
            continue  # not yet read together with everything that belongs with it; never given out half-understood
        out.append(
            {
                "src": "documents",
                "id": r["id"],
                "kind": facts.get("kind", "other"),
                "title": store.proper_name(facts, r["name"], facts.get("kind", "")),
                "party": str(facts.get("party") or ""),
                "date": str(facts.get("date") or facts.get("start_date") or ""),
                "due": str(facts.get("due_date") or ""),
                "end": str(facts.get("end_date") or ""),
                "amount": _amount(facts),
                "currency": str(facts.get("currency") or ""),
                "reference": str(facts.get("reference") or ""),
                "place": str(facts.get("place") or ""),
                "followup": str((facts.get("health") or {}).get("follow_up") or ""),
                "absent": list(facts.get("absent", [])),
            }
        )
    out.extend(_matters(conn))
    for t in travel.trips(conn, state.engine(), today):
        out.append(
            {
                "src": "documents",
                "kind": "trip",
                "title": t["place"],
                "place": t["place"],
                "date": t["start"],
                "end": t["end"],
                "photos": t.get("photos", 0),
                "documents": t.get("documents", 0),
            }
        )
    return out
