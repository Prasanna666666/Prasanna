"""Auto-tagging of notes. Rules first (instant, deterministic), then an optional local-model suggestion.

Never overwrites tags the user set: only notes with no tags are touched. The model may only choose from VOCAB, so it
cannot invent tags or smuggle text into the database.
"""

from __future__ import annotations

import json
import re

VOCAB = ("health", "family", "money", "home", "work", "travel", "ideas", "shopping", "learning", "documents")

RULES: dict[str, tuple[str, ...]] = {
    "health": ("doctor", "medicine", "tablet", "bp", "sugar", "diabetes", "hospital", "prescription", "dose",
               "checkup", "check-up", "appointment", "blood", "clinic", "dentist"),
    "money": ("rent", "bill", "bank", "salary", "invoice", "emi", "loan", "tax", "insurance", "payment", "budget",
              "rupees", "refund"),
    "home": ("repair", "plumber", "electrician", "warranty", "appliance", "ac", "fridge", "landlord", "maintenance"),
    "travel": ("flight", "ticket", "hotel", "trip", "passport", "visa", "train", "booking"),
    "shopping": ("buy", "grocery", "groceries", "order", "shopping"),
    "work": ("meeting", "project", "client", "deadline", "office", "boss"),
    "learning": ("course", "book", "read", "learn", "study"),
    "documents": ("aadhaar", "pan", "passport", "license", "certificate", "policy number"),
    "ideas": ("idea", "maybe", "someday", "what if"),
}


def _has(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None


def rule_tags(text: str, people: list[dict]) -> list[str]:
    t = text.lower()
    tags = [tag for tag, words in RULES.items() if any(_has(t, w) for w in words)]
    for p in people:
        first = p["name"].split()[0].lower() if p["name"].strip() else ""
        if first and _has(t, first):
            tags += [first, "family"]
    return sorted(set(tags))


def model_tags(client, model: str, text: str) -> list[str]:
    msg = client.chat(model, [
        {"role": "system", "content": "Pick up to 3 tags for the note from this list only: " + ", ".join(VOCAB) +
         '. Reply with a JSON array of strings, e.g. ["health","family"]. No other text.'},
        {"role": "user", "content": text[:1500]}])
    m = re.search(r"\[.*?\]", msg.get("content") or "", re.S)
    try:
        found = json.loads(m.group(0)) if m else []
    except ValueError:
        found = []
    return [t for t in found if isinstance(t, str) and t.lower() in VOCAB][:3]


def autotag_notes(conn, client=None, model: str | None = None) -> int:
    """Tag every note that has no tags. Returns how many notes were tagged."""
    people = [dict(r) for r in conn.execute("SELECT name FROM people")]
    done = 0
    for n in conn.execute("SELECT id, title, body FROM notes WHERE tags=''").fetchall():
        text = f"{n['title']} {n['body']}"
        tags = rule_tags(text, people)
        if not tags and client is not None and model:
            tags = [t.lower() for t in model_tags(client, model, text)]
        if tags:
            conn.execute("UPDATE notes SET tags=? WHERE id=?", (",".join(sorted(set(tags))), n["id"]))
            done += 1
    conn.commit()
    return done
