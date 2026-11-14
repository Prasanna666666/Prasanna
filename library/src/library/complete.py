"""Completing the understanding. A document read on its own often leaves a field open: an attachment that does not say who sent it (the mail did), a receipt with no payee (the invoice
it settles has it), a booking with no place (the ticket next to it has it). Before anything is shown, the missing fields are looked for in everything that belongs with the document:
the same mail and its other attachments, other documents with the same reference, and then, as one targeted question to the model about the document together with that context.
A value is kept only when the context actually says it. What no source says is recorded as absent: the document is then fully understood (it simply does not state that), and it
is shown as what it is, never guessed."""

from __future__ import annotations

import json
from typing import Any

from kit import extract

from . import understood

MAX_TRIES = 2
SHARED = ("party", "place", "start_date", "end_date", "currency")  # facts that belong to the whole case, not to one page of it


def _related(conn, row) -> list[dict[str, Any]]:
    """The other documents that belong with this one: the same mail (its other attachments) and the same reference."""
    facts = json.loads(row["facts"])
    prefix = row["name"].rsplit("/", 1)[0] if "/" in row["name"] else ""
    ref = str(facts.get("reference") or "").strip()
    rows = conn.execute(
        "SELECT id, name, facts, text FROM documents WHERE id<>? AND judged=1 AND facts<>'' AND (name LIKE ? ESCAPE '\\' OR name=? OR (?<>'' AND facts LIKE ?))",
        (row["id"], (prefix.replace("%", "\\%").replace("_", "\\_") + "/%") if prefix else "\x00", prefix or "\x00", ref, f'%"reference": "{ref}"%'),
    ).fetchall()
    return [{"id": r["id"], "facts": json.loads(r["facts"]), "text": r["text"]} for r in rows]


def _from_related(facts: dict[str, Any], related: list[dict[str, Any]], missing: list[str]) -> list[str]:
    """Fill what the same case already knows. Returns the fields still missing."""
    still = []
    for field in missing:
        key = {
            "who it is from": "party",
            "the amount": "total",
            "the date": "start_date" if facts.get("kind") in ("ticket", "booking") else "date",
            "the place": "place",
            "the period": "period",
        }[field]
        value = next((r["facts"].get(key) for r in related if r["facts"].get(key) not in (None, "", [])), None)
        if value is not None and (key in SHARED or key == "total"):
            facts[key] = value
        else:
            still.append(field)
    return still


def _ask_with_context(client, model: str, name: str, text: str, related: list[dict[str, Any]], missing: list[str]) -> dict[str, Any]:
    """One targeted question: the document together with what belongs with it. Answers are kept only if the context says them."""
    context = "\n".join(
        f"[related] {json.dumps({k: v for k, v in r['facts'].items() if k in SHARED or k in ('kind', 'title', 'date', 'total')})}" for r in related[:5]
    )
    body = f"File name: {name}\n{context}\n\n{extract.sample_of(text)}"
    schema = {"type": "object", "properties": {k: {"type": ["string", "null"]} for k in ("party", "place", "date", "total", "period")}}
    prompt = (
        f"This document is missing: {', '.join(missing)}. Using the document and the related facts, give only what is written there (party = who it is from, place, date as YYYY-MM-DD, "
        "total exactly as printed, period). Use null for anything not stated. Never guess."
    )
    try:
        return extract._ask(client, model, prompt, body, schema)
    except extract.Unclear:
        return {}


def _verified(facts: dict[str, Any], answer: dict[str, Any], text: str, related: list[dict[str, Any]]) -> None:
    haystack = text + " " + " ".join(json.dumps(r["facts"]) for r in related)
    low = haystack.lower()
    party = str(answer.get("party") or "").strip()
    if party and not facts.get("party") and party.lower() in low:
        facts["party"] = party
    place = str(answer.get("place") or "").strip()
    if place and not facts.get("place") and place.lower() in low:
        facts["place"] = place
    day = str(answer.get("date") or "")
    if day and day in extract.dates_in(haystack):
        facts.setdefault("start_date" if facts.get("kind") in ("ticket", "booking") else "date", day)
    total = extract.verify_amounts({"total": answer.get("total")}, haystack).get("total")
    if total is not None and facts.get("total") in (None, ""):
        facts["total"] = total


def complete_one(conn, client, model, row) -> bool:
    """Look for what a document leaves open, in everything that belongs with it. Returns True when it changed."""
    facts = json.loads(row["facts"])
    ok, missing = understood.check(facts)
    if ok:
        return False
    related = _related(conn, row)
    before = json.dumps(facts, sort_keys=True)
    still = _from_related(facts, related, missing)
    if still and client is not None and model:
        _verified(facts, _ask_with_context(client, model, row["name"], row["text"], related, still), row["text"], related)
    facts["completion_tries"] = int(facts.get("completion_tries", 0)) + 1
    ok, missing = understood.check(facts)
    if not ok and facts["completion_tries"] >= MAX_TRIES:
        facts["absent"] = sorted(set(facts.get("absent", [])) | set(missing))  # looked for everywhere: the document does not state it
    conn.execute("UPDATE documents SET facts=? WHERE id=?", (json.dumps(facts), row["id"]))
    return json.dumps(facts, sort_keys=True) != before


def complete_pending(conn, client, model, limit: int = 20) -> int:
    """Complete the documents that were understood but left something open. A few at a time: it is one small question each, and only for the ones that need it."""
    done = 0
    for row in conn.execute("SELECT id, name, text, facts FROM documents WHERE judged=1 AND facts<>'' AND kind<>'email' ORDER BY id"):
        facts = json.loads(row["facts"])
        if understood.check(facts)[0] or int(facts.get("completion_tries", 0)) >= MAX_TRIES:
            continue
        complete_one(conn, client, model, row)
        done += 1
        if done >= limit:
            break
    conn.commit()
    return done
