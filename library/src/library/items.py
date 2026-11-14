"""What the documents and mails say, as plain dated items (who, what, when, how much, which reference), for Atlas to join with what other parts know. Facts only, checked ones:
a reading that is only partial is not given out."""

from __future__ import annotations

import json
from typing import Any

from . import store, travel, understood

MAX_ITEMS = 3000


def _amount(facts: dict) -> float | None:
    total = facts.get("total")
    return float(total) if isinstance(total, int | float) else None


def items(conn, state: Any, today: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in conn.execute("SELECT id, name, area, facts FROM documents WHERE judged=1 AND facts<>'' ORDER BY ready DESC LIMIT ?", (MAX_ITEMS,)):
        facts = json.loads(r["facts"])
        if not understood.check(facts)[0]:
            continue  # not understood yet (it is being completed from what belongs with it); never given out half-read
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
