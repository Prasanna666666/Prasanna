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
from collections.abc import Callable
from typing import Any

from kit import extract

ID = re.compile(r"\b(?=[A-Za-z0-9/\-]*\d)[A-Za-z0-9][A-Za-z0-9/\-]{4,}\b")
AMOUNT = re.compile(r"\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b")
WORD = re.compile(r"[^\W\d_]{6,}")
RARE = 4  # a value that appears in more pieces than this says nothing about which pieces belong together
MAX_CONFIRMS = 20  # model checks per round, so the computer stays responsive; the rest wait for the next round
OVERLAP = 300
BATCH_CHARS = 6000  # what one model call reads; a matter bigger than this is read in several calls, nothing is cut


def _rare_values(text: str) -> set[str]:
    return {m.lower() for m in ID.findall(text)} | {m.lower() for m in AMOUNT.findall(text)} | {m.lower() for m in WORD.findall(text)}


def _mail_of(name: str) -> str:
    return name.rsplit("/", 1)[0] if "/" in name else ""


def _shared(pieces: list[dict[str, Any]]) -> set[tuple[int, int]]:
    """Pairs of pieces that share a value few other pieces have: the only job here is to pick which pieces the model is shown together."""
    index: dict[str, list[int]] = defaultdict(list)
    for p in pieces:
        for v in _rare_values(f"{p['name']} {p['text']}"):
            index[v].append(p["id"])
    return {(a, b) for ids in index.values() if 2 <= len(ids) <= RARE for i, a in enumerate(ids) for b in ids[i + 1 :]}


def candidates(pieces: list[dict[str, Any]]) -> list[tuple[int, int, bool]]:
    """Pairs worth showing the model: (a, b, same_mail). Pieces of one mail belong together by fact; the rest are only candidates until the model has read them."""
    names = {p["id"]: p["name"] for p in pieces}
    out = []
    for a, b in sorted(_shared(pieces)):
        out.append((a, b, bool(_mail_of(names[a])) and _mail_of(names[a]) == _mail_of(names[b])))
    for ids in _by_mail(pieces).values():
        out.extend((a, b, True) for i, a in enumerate(ids) for b in ids[i + 1 :] if (a, b) not in _shared(pieces))
    return out


def _by_mail(pieces: list[dict[str, Any]]) -> dict[str, list[int]]:
    by_mail: dict[str, list[int]] = defaultdict(list)
    for p in pieces:
        if _mail_of(p["name"]):
            by_mail[_mail_of(p["name"])].append(p["id"])
    return by_mail


def link(pieces: list[dict[str, Any]], verdict: Callable[[int, int], bool | None]) -> tuple[list[list[int]], set[int]]:
    """Groups of pieces that belong together, and the pieces whose links are still undecided. Two pieces are joined only if they are of the same mail or
    `verdict` confirms them (True), never on a guess; None means not yet decided, and those pieces are held back rather than shown on a guess."""
    parent = {p["id"]: p["id"] for p in pieces}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    undecided: set[int] = set()
    for a, b, same in candidates(pieces):
        if find(a) == find(b):
            continue
        said = True if same else verdict(a, b)
        if said is None:
            undecided.update((a, b))
        elif said:
            parent[find(a)] = find(b)
    groups: dict[int, list[int]] = defaultdict(list)
    for p in pieces:
        groups[find(p["id"])].append(p["id"])
    return [sorted(g) for g in groups.values() if not undecided.intersection(g)], undecided


SAME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"same": {"type": "boolean"}, "quote_a": {"type": "string"}, "quote_b": {"type": "string"}},
    "required": ["same"],
}
SAME_PROMPT = (
    "Are these two pieces of someone's papers about the SAME single matter (the same bill, trip, appointment, contract, purchase...), "
    "not just similar or from the same sender? If yes, copy from each piece the exact words that show it is the same matter (a shared reference, "
    "the same item, the same event). If you cannot, answer false."
)


def confirm(client: Any, model: str, a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Same matter? Only if the model says so AND both quotes are really in their pieces. Raises Unclear when the model cannot answer."""
    body = f"[A] {a['name']}\n{a['text'][:BATCH_CHARS]}\n\n[B] {b['name']}\n{b['text'][:BATCH_CHARS]}"
    data = extract._ask(client, model, SAME_PROMPT, body, SAME_SCHEMA)
    return bool(data.get("same")) and _quoted(data.get("quote_a"), a["text"] + a["name"]) and _quoted(data.get("quote_b"), b["text"] + b["name"])


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


def _windows(text: str) -> list[str]:
    """Windows that start and end on whitespace and overlap, so no number or sentence is cut in half between two calls."""
    if len(text) <= BATCH_CHARS:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(start + BATCH_CHARS, len(text))
        if end < len(text):
            end = text.rfind(" ", start + BATCH_CHARS // 2, end) + 1 or end
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
        start = text.find(" ", start) + 1 or start
    return out


def _batches(pieces: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Every character of every piece goes into exactly one batch: long pieces are split in windows, nothing is dropped."""
    parts = [{"name": p["name"], "text": w} for p in pieces for w in _windows(p["text"])]
    out: list[list[dict[str, Any]]] = [[]]
    used = 0
    for part in parts:
        if out[-1] and used + len(part["text"]) > BATCH_CHARS:
            out.append([])
            used = 0
        out[-1].append(part)
        used += len(part["text"])
    return out


def synthesize(client: Any, model: str, pieces: list[dict[str, Any]]) -> dict[str, Any]:
    """Read ALL of a matter, in as many calls as it takes, and merge. `coverage` is the share of its text that was read (1.0 only when every character was);
    several different statuses are all kept, never one picked by guessing."""
    reads = [_read_batch(client, model, b) for b in _batches(pieces)]
    total = sum(len(p["text"]) for p in pieces) or 1
    out: dict[str, Any] = {"title": reads[0]["title"], "what": reads[0]["what"], "verified": sum(r["verified"] for r in reads), "pieces": len(pieces)}
    out["dates"] = [d for r in reads for d in r["dates"]]
    out["amounts"] = [a for r in reads for a in r["amounts"]]
    statuses = sorted({r["status"] for r in reads if r.get("status")})
    if statuses:
        out["status"] = statuses[0] if len(statuses) == 1 else " / ".join(statuses)
        out["conflict"] = len(statuses) > 1
        out["open"] = any(r.get("open") for r in reads if r.get("status"))
    nexts = [r["next"] for r in reads if r.get("next")]
    if nexts:
        out["next"] = min(nexts, key=lambda n: n["date"])
    out["coverage"] = min(1.0, sum(len(x["text"]) for b in _batches(pieces) for x in b) / total)
    return out


def _read_batch(client: Any, model: str, shown: list[dict[str, Any]]) -> dict[str, Any]:
    """One model call over a batch. Everything returned has been checked against the batch: a claim without a real quote is dropped."""
    body = "\n\n".join(f"[P{i + 1}] {p['name']}\n{p['text']}" for i, p in enumerate(shown))
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
    for r in conn.execute("SELECT id, name, sha256, text, facts FROM documents WHERE judged=1 AND (TRIM(text)<>'' OR facts<>'')"):
        facts = json.loads(r["facts"]) if r["facts"] else {}
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "sha": r["sha256"],
                "text": (r["text"] or "") + " " + " ".join(f"{k} {v}" for k, v in facts.items() if isinstance(v, str | int | float)),
            }
        )
    return out


def _hash(group: list[int], pieces: dict[int, dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for pid in group:
        h.update(f"{pid}:{pieces[pid]['sha']}".encode())  # the content, not its current length: reducing a mail afterwards must not make the matter new
    return h.hexdigest()[:20]


def _verdicts(conn, client: Any, model: str, by_id: dict[int, dict[str, Any]]) -> Callable[[int, int], bool | None]:
    """Earlier answers are remembered by the content of both pieces; new ones are asked, a limited number per round."""
    budget = [MAX_CONFIRMS if client is not None else 0]

    def verdict(a: int, b: int) -> bool | None:
        key = sorted((by_id[a]["sha"], by_id[b]["sha"]))
        row = conn.execute("SELECT same FROM links WHERE sha_a=? AND sha_b=?", key).fetchone()
        if row is not None:
            return bool(row["same"])
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        try:
            same = confirm(client, model, by_id[a], by_id[b])
        except extract.Unclear:
            return None
        conn.execute("INSERT OR REPLACE INTO links (sha_a, sha_b, same) VALUES (?,?,?)", (*key, int(same)))
        return same

    return verdict


def rebuild(conn, client: Any = None, model: str = "") -> int:
    """Group the pieces into matters. A matter whose pieces did not change keeps what was already understood; changed or new ones are queued to be read again."""
    pieces = pieces_of(conn)
    by_id = {p["id"]: p for p in pieces}
    now: dict[str, list[int]] = {_hash(g, by_id): g for g in link(pieces, _verdicts(conn, client, model, by_id))[0]}
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


def open_matters(conn) -> list[dict[str, Any]]:
    """The matters still open, the ones with a date first (soonest), each as the model understood it."""
    out = []
    for r in conn.execute("SELECT id, summary FROM cases WHERE summary<>''"):
        s = json.loads(r["summary"])
        if s.get("open"):
            out.append({"id": r["id"], "title": s["title"], "status": s.get("status", ""), "next": s.get("next") or {}})
    return sorted(out, key=lambda m: (not m["next"], m["next"].get("date", "")))
