"""Auto-tagging of notes. The people named in a note come from the people list; the topic tags are chosen by the local model from `tags.json`.

Never overwrites tags the user set: a note that already has a topic tag is left alone. The model may only choose from VOCAB, so it
cannot invent tags or smuggle text into the database. There are no word lists: what a note is about is the model's decision.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "tags.json").read_text(encoding="utf-8"))
VOCAB: tuple[str, ...] = tuple(_DATA["vocab"])
MAX_TAGS = 3  # topic tags one note gets
NOTE_CHARS = 1500  # how much of a note the model reads


def _has(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None


def people_tags(text: str, people: list[dict]) -> list[str]:
    """The first names from the people list that appear in the text, each with "family"."""
    t = text.lower()
    tags: list[str] = []
    for p in people:
        first = p["name"].split()[0].lower() if p["name"].strip() else ""
        if first and _has(t, first):
            tags += [first, "family"]
    return sorted(set(tags))


def model_tags(client, model: str, text: str) -> list[str]:
    msg = client.chat(
        model,
        [
            {
                "role": "system",
                "content": f"Pick up to {MAX_TAGS} tags for the note from this list only: "
                + ", ".join(VOCAB)
                + '. Reply with a JSON array of strings, e.g. ["health","family"]. No other text.',
            },
            {"role": "user", "content": text[:NOTE_CHARS]},
        ],
    )
    m = re.search(r"\[.*?\]", msg.get("content") or "", re.DOTALL)
    try:
        found = json.loads(m.group(0)) if m else []
    except ValueError:
        found = []
    return [t for t in found if isinstance(t, str) and t.lower() in VOCAB][:MAX_TAGS]


def autotag_notes(conn, client=None, model: str | None = None) -> int:
    """Give every note without a topic tag its people and the model's choice of topics. Without a model only the people are added. Returns how many notes were tagged."""
    people = [dict(r) for r in conn.execute("SELECT name FROM people")]
    done = 0
    for n in conn.execute("SELECT id, title, body, tags FROM notes").fetchall():
        have = {t for t in str(n["tags"]).split(",") if t}
        if have & set(VOCAB):
            continue  # already has a topic: the person's own, or an earlier choice
        text = f"{n['title']} {n['body']}"
        tags = have | set(people_tags(text, people))
        if client is not None and model:
            tags |= {t.lower() for t in model_tags(client, model, text)}
        if tags != have:
            conn.execute("UPDATE notes SET tags=? WHERE id=?", (",".join(sorted(tags)), n["id"]))
            done += 1
    conn.commit()
    return done
