"""The casebook: the pieces of one matter, found wherever they are, put together, and understood as a whole.

A document can stand alone or be one piece among several in several places (a mail, its attachment, a reminder, the receipt, a report that followed). Nothing here knows
what a "bill" or a "trip" is. Pieces are linked by what they share that is distinctive (a number that appears in only a few of them, an amount, a rare name, the mail they
came in), the pieces of one matter are read together by the model, and every claim it makes must come with a quote that really is in a piece. What cannot be quoted is dropped.
A matter is understood when it has been read as a whole and its claims check out."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from kit import extract

ID = re.compile(r"\b(?=[A-Za-z0-9/\-]*\d)[A-Za-z0-9][A-Za-z0-9/\-]{4,}\b")
AMOUNT = re.compile(r"\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b")
WORD = re.compile(r"[^\W\d_]{6,}")
RARE = 4  # a value that appears in more pieces than this says nothing about which pieces belong together
LINK_AT = 3.0  # how much shared, distinctive evidence two pieces need before they are one matter
WEIGHT: dict[str, float] = {"id": 3.0, "amount": 1.5, "word": 1.0, "mail": 3.0}
PIECE_CHARS = 1500
MAX_PIECES = 6


def _cents(text: str) -> str:
    digits = re.sub(r"[.,](?=\d{3}\b)", "", text)
    return digits.replace(",", ".")


def features(text: str) -> dict[str, set[str]]:
    return {
        "id": {m.lower() for m in ID.findall(text)},
        "amount": {_cents(m) for m in AMOUNT.findall(text)},
        "word": {m.lower() for m in WORD.findall(text)},
    }


def _mail_of(name: str) -> str:
    return name.rsplit("/", 1)[0] if "/" in name else ""


def _scores(pieces: list[dict[str, Any]]) -> dict[tuple[int, int], float]:
    index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for p in pieces:
        for kind, values in features(f"{p['name']} {p['text']}").items():
            for v in values:
                index[(kind, v)].append(p["id"])
    score: dict[tuple[int, int], float] = defaultdict(float)
    for (kind, _), ids in index.items():
        if 2 <= len(ids) <= RARE:
            for i, a in enumerate(ids):
                for b in ids[i + 1 :]:
                    score[(a, b)] += WEIGHT[kind]
    by_mail: dict[str, list[int]] = defaultdict(list)
    for p in pieces:
        if _mail_of(p["name"]):
            by_mail[_mail_of(p["name"])].append(p["id"])
    for ids in by_mail.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                score[(a, b)] += WEIGHT["mail"]
    return score


def link(pieces: list[dict[str, Any]]) -> list[list[int]]:
    """Groups of piece ids that belong together. Pure: shared distinctive values and shared mail, nothing about kinds of documents."""
    parent = {p["id"]: p["id"] for p in pieces}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), s in _scores(pieces).items():
        if s >= LINK_AT:
            parent[find(a)] = find(b)
    groups: dict[int, list[int]] = defaultdict(list)
    for p in pieces:
        groups[find(p["id"])].append(p["id"])
    return [sorted(g) for g in groups.values()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold().strip()


def _quoted(quote: Any, text: str) -> bool:
    q = _norm(str(quote or ""))
    return len(q) >= 3 and q in _norm(text)


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "what": {"type": "string"},
        "open": {"type": "boolean"},
        "status": {"type": "string"},
        "status_piece": {"type": "integer"},
        "status_quote": {"type": "string"},
        "dates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "date": {"type": "string"}, "piece": {"type": "integer"}, "quote": {"type": "string"}},
            },
        },
        "amounts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "value": {"type": "string"}, "piece": {"type": "integer"}, "quote": {"type": "string"}},
            },
        },
        "next": {
            "type": "object",
            "properties": {"what": {"type": "string"}, "date": {"type": "string"}, "piece": {"type": "integer"}, "quote": {"type": "string"}},
        },
    },
    "required": ["title", "what"],
}
PROMPT = (
    "These are the pieces of ONE matter in someone's papers, from different places (mails, attachments, documents). Read them together. Say what the matter is (title, and what "
    "it is about in one sentence), whether anything about it is still open or pending (open true/false) and its status in a few words, every date that matters and every amount, and "
    "what happens next and when. EVERY date, amount, the status and the next step must come with the number of the piece it is in and a short quote copied exactly from that piece. "
    "Leave out whatever the pieces do not say. Never guess."
)


def synthesize(client: Any, model: str, pieces: list[dict[str, Any]]) -> dict[str, Any]:
    """Read the pieces of one matter together. Everything returned has been checked against the pieces: a claim without a real quote is dropped."""
    shown = sorted(pieces, key=lambda p: -len(p["text"]))[:MAX_PIECES]
    body = "\n\n".join(f"[P{i + 1}] {p['name']}\n{p['text'][:PIECE_CHARS]}" for i, p in enumerate(shown))
    data = extract._ask(client, model, PROMPT, body, SCHEMA)

    def text_of(n: Any) -> str:
        return shown[n - 1]["text"] if isinstance(n, int) and 1 <= n <= len(shown) else ""

    out: dict[str, Any] = {"title": str(data.get("title") or "")[:120], "what": str(data.get("what") or "")[:300], "verified": 0}
    if not out["title"] or not out["what"]:
        raise extract.Unclear("no title and no account of what it is")
    for key in ("dates", "amounts"):
        kept = []
        for item in data.get(key) or []:
            if not isinstance(item, dict) or not _quoted(item.get("quote"), text_of(item.get("piece"))):
                continue
            value = str(item.get("date" if key == "dates" else "value") or "")
            if key == "dates" and value not in extract.dates_in(text_of(item["piece"])):
                continue
            if key == "amounts" and _norm(value).replace(" ", "") not in _norm(text_of(item["piece"])).replace(" ", ""):
                continue
            kept.append({"label": str(item.get("label") or "")[:60], "value": value, "quote": str(item["quote"])[:160]})
        out[key] = kept
        out["verified"] += len(kept)
    if _quoted(data.get("status_quote"), text_of(data.get("status_piece"))):
        out["status"], out["open"], out["status_quote"] = str(data.get("status") or "")[:80], bool(data.get("open")), str(data["status_quote"])[:160]
        out["verified"] += 1
    raw = data.get("next")
    nxt: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if str(nxt.get("date")) in extract.dates_in(text_of(nxt.get("piece"))) and _quoted(nxt.get("quote"), text_of(nxt.get("piece"))):
        out["next"] = {"what": str(nxt.get("what") or "")[:120], "date": nxt["date"], "quote": str(nxt["quote"])[:160]}
        out["verified"] += 1
    return out


def pieces_of(conn) -> list[dict[str, Any]]:
    """Everything read that can say something: the documents, the mails (what they say), the attachments."""
    out = []
    for r in conn.execute("SELECT id, name, text, facts FROM documents WHERE judged=1 AND kind<>'image' AND (TRIM(text)<>'' OR facts<>'')"):
        facts = json.loads(r["facts"]) if r["facts"] else {}
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "text": (r["text"] or "") + " " + " ".join(f"{k} {v}" for k, v in facts.items() if isinstance(v, str | int | float)),
            }
        )
    return out


def _hash(group: list[int], pieces: dict[int, dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for pid in group:
        h.update(f"{pid}:{len(pieces[pid]['text'])}".encode())
    return h.hexdigest()[:20]


def rebuild(conn) -> int:
    """Group the pieces into matters. A matter whose pieces did not change keeps what was already understood; changed or new ones are queued to be read again."""
    pieces = pieces_of(conn)
    by_id = {p["id"]: p for p in pieces}
    now: dict[str, list[int]] = {_hash(g, by_id): g for g in link(pieces)}
    known = {r["input_hash"] for r in conn.execute("SELECT input_hash FROM cases")}
    for h in known - set(now):
        conn.execute("DELETE FROM cases WHERE input_hash=?", (h,))
    new = 0
    for h, members in now.items():
        if h not in known:
            conn.execute("INSERT INTO cases (input_hash, members, summary, tries) VALUES (?,?,?,0)", (h, json.dumps(members), ""))
            new += 1
    conn.execute("UPDATE documents SET case_id=NULL")
    for r in conn.execute("SELECT id, members FROM cases WHERE summary<>''").fetchall():
        for pid in json.loads(r["members"]):
            conn.execute("UPDATE documents SET case_id=? WHERE id=?", (r["id"], pid))
    conn.commit()
    return new


def understand_pending(conn, client: Any, model: str, limit: int = 5) -> int:
    """Read matters not yet understood, a few at a time: the pieces together, the claims checked. A matter the model cannot make sense of is tried again next time."""
    by_id = {p["id"]: p for p in pieces_of(conn)}
    done = 0
    for row in conn.execute("SELECT id, members FROM cases WHERE summary='' AND tries<3 ORDER BY id").fetchall():
        members = [by_id[m] for m in json.loads(row["members"]) if m in by_id]
        if not members:
            continue
        try:
            summary = synthesize(client, model, members)
        except extract.Unclear:
            conn.execute("UPDATE cases SET tries=tries+1 WHERE id=?", (row["id"],))
            continue
        conn.execute("UPDATE cases SET summary=? WHERE id=?", (json.dumps(summary), row["id"]))
        for m in members:
            conn.execute("UPDATE documents SET case_id=? WHERE id=?", (row["id"], m["id"]))
        done += 1
        if done >= limit:
            break
    conn.commit()
    return done
