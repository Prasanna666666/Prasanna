"""The one store of everything that was read: every file and every mail, once, with what it is and what it says.

The sealed reader (parser.py, no network) turns files into plain JSON; this module takes that JSON into the encrypted database, deletes the readable
copy, and has the local model say what each document is. Code verifies every amount and every date against the document's own text (extract.py).
Other apps (Finance today; Health, Travel and others later) do not read files themselves: they ask this store for the kinds of documents that are relevant to them.

A document is judged once: read by the model (`judged = 1`), or not worth the model's time (`judged = 2`, a newsletter). Either way it gets a `ready`
number, so an app that asks "what is new since number N?" never misses a document that was judged after a later one arrived.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from kit import extract, rag
from kit.module import Module

from . import recognise, relevance

MIGRATIONS = (
    """
    CREATE TABLE documents (
        id INTEGER PRIMARY KEY,
        sha256 TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,                      -- how it was read: pdf, image, email, sheet ...
        text TEXT NOT NULL,
        area TEXT NOT NULL DEFAULT '',           -- where it came from: a collection folder you named (finance, health ...), 'mail', or '' (the inbox)
        data TEXT NOT NULL DEFAULT '',           -- structured rows or lines, as JSON
        parsed_at TEXT,
        facts TEXT NOT NULL DEFAULT '',          -- what the model said it is (kind, who, when, how much), every amount and date verified, as JSON
        judged INTEGER NOT NULL DEFAULT 0,       -- 0 not yet, 1 read by the model, 2 not worth it
        ready INTEGER,                           -- the order in which documents became ready
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX documents_ready ON documents (ready);
    """,
)
MODULE = Module("library", MIGRATIONS)
FILE_KINDS = {"text", "csv", "pdf", "image", "sheet", "doc", "html", "email", "json"}
MAX_JSON = 30_000_000
MAX_TEXT = 2_000_000
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COLLECTION = re.compile(r"^[a-z]{2,20}$")
Progress = Callable[[str], None]


def _valid(d: Any, stem: str) -> bool:
    return bool(
        isinstance(d, dict)
        and d.get("schema") == 1
        and isinstance(d.get("sha256"), str)
        and _SHA.match(d["sha256"])
        and stem == d["sha256"]
        and d.get("kind") in FILE_KINDS
        and isinstance(d.get("name"), str)
        and 0 < len(d["name"]) <= 255
        and isinstance(d.get("text"), str)
        and len(d["text"]) <= MAX_TEXT
    )


def _structured(d: dict) -> str:
    keep = {
        k: d["data"][k]
        for k in ("rows", "lines", "table", "table_pdfplumber", "table_poppler")
        if isinstance(d.get("data"), dict) and isinstance(d["data"].get(k), list)
    }
    if isinstance(d.get("meta"), dict) and d["meta"]:
        keep["meta"] = d["meta"]  # how it was read: scanned, how confident, how many pages
    return json.dumps(keep) if keep else ""


def ingest_dir(conn, directory: Path) -> dict[str, int]:
    """Take the reader's output into the database. Strict: anything unexpected is skipped, never partially trusted. The readable copy is deleted once stored."""
    new = known = rejected = 0
    stored: list[Path] = []
    for f in sorted(directory.resolve().glob("*.json")):
        try:
            if f.is_symlink() or f.stat().st_size > MAX_JSON:
                raise ValueError("symlink or too large")
            d = json.loads(f.read_text(encoding="utf-8"))
            if not _valid(d, f.stem):
                raise ValueError("schema")
        except (ValueError, OSError):
            rejected += 1
            continue
        area = d["area"] if isinstance(d.get("area"), str) and (d["area"] == "mail" or _COLLECTION.match(d["area"])) else ""
        cur = conn.execute(
            "INSERT OR IGNORE INTO documents (sha256, name, kind, text, area, data, parsed_at) VALUES (?,?,?,?,?,?,?)",
            (d["sha256"], d["name"], d["kind"], d["text"], area, _structured(d), str(d.get("parsed_at", ""))[:25]),
        )
        new += cur.rowcount
        known += 1 - cur.rowcount
        stored.append(f)
    conn.commit()
    if os.access(directory, os.W_OK):
        for f in stored:  # the text now lives only in the encrypted database
            f.unlink(missing_ok=True)
    return {"new": new, "known": known, "rejected": rejected}


# ---- judging: what is each document? ------------------------------------------------------------------------------------------
def _mark_ready(conn, sha: str, judged: int, facts: dict | None) -> None:
    conn.execute(
        "UPDATE documents SET judged=?, facts=?, ready=(SELECT COALESCE(MAX(ready),0)+1 FROM documents) WHERE sha256=?",
        (judged, json.dumps(facts) if facts else "", sha),
    )


def _data(d) -> dict:
    try:
        return json.loads(d["data"]) if d["data"] else {}
    except ValueError:
        return {}


def _exact_facts(d) -> dict | None:
    """Documents that need no model: a bank standard (MT940, camt.053), the ECB's exchange-rate file, or a picture with no text in it (a photo)."""
    if recognise.bank_standard(d["text"]):
        return {"kind": "bank_statement", "title": "Bank statement"}
    if recognise.exchange_rate_file(_data(d).get("rows")):
        return {"kind": "other", "title": "ECB exchange rates"}
    if d["kind"] == "image" and len(d["text"].strip()) < relevance.MIN_TEXT:  # a picture with no text in it is a photo, not a document: Photos' business
        return {"kind": "photo", "title": d["name"]}
    return None


def judge_pending(conn, client, model, progress: Progress | None = None) -> dict[str, Any]:
    """Judge every document not yet judged. Files from a collection folder you named, and anything else with text worth reading, go to the model; the rest is marked and left alone.
    If the model cannot be reached the document stays as it is and the next round tries again."""
    pending = conn.execute("SELECT sha256, name, kind, text, data, area FROM documents WHERE judged=0 ORDER BY id").fetchall()
    out: dict[str, Any] = {"read": 0, "skipped": 0, "waiting": 0, "problem": ""}
    for index, d in enumerate(pending, 1):
        exact = _exact_facts(d)
        if exact is not None:
            _mark_ready(conn, d["sha256"], 1, exact)
        elif d["area"] in ("", "mail") and not relevance.worth_reading(d["name"], d["kind"], d["text"]):
            _mark_ready(conn, d["sha256"], 2, None)
            out["skipped"] += 1
            continue
        else:
            if client is None or not model:
                out["waiting"] += 1
                out["problem"] = "The local model is not running, so new files cannot be read yet. Start Ollama and press Update again."
                continue
            if progress and index % 5 == 1:
                progress(f"Reading {index} of {len(pending)}")
            try:
                facts = extract.classify(client, model, d["name"], d["text"])
            except RuntimeError as exc:  # the model could not be reached: nothing is marked as done
                out["waiting"] = len(pending) - index + 1
                out["problem"] = str(exc)
                break
            _mark_ready(conn, d["sha256"], 1, facts)
        out["read"] += 1
        if index % 20 == 0:
            conn.commit()
    conn.commit()
    return out


# ---- asking: what any app can take -------------------------------------------------------------------------------------------
LIST_COLUMNS = "id, sha256, name, kind, area, parsed_at, facts, ready"


def _as_document(r) -> dict[str, Any]:
    facts = json.loads(r["facts"]) if r["facts"] else {}
    doc: dict[str, Any] = {
        "id": r["id"],
        "sha256": r["sha256"],
        "name": r["name"],
        "file_kind": r["kind"],
        "area": r["area"],
        "kind": facts.get("kind", "other"),
        "facts": facts,
        "ready": r["ready"],
    }
    return doc


def list_documents(
    conn, kinds: list[str] | None = None, area: str = "", place: str = "", year: str = "", since: int = 0, limit: int = 100, full: bool = False
) -> list[dict]:
    """Ready documents, oldest first. `kinds` are classified kinds (invoice, ticket, medical ...); a document is returned when its kind is listed or, with `area`, when it came from that area.
    Without either, everything the model recognised (not "other") is returned. With `full`, the text and structured data come too."""
    wanted = set(kinds or [])
    out: list[dict] = []
    for r in conn.execute(f"SELECT {LIST_COLUMNS} FROM documents WHERE ready > ? ORDER BY ready", (max(0, int(since)),)):
        doc = _as_document(r)
        if wanted or area:
            if doc["kind"] not in wanted and not (area and doc["area"] == area):
                continue
        elif doc["kind"] == "other":
            continue
        facts = doc["facts"]
        if place and place.lower() not in str(facts.get("place", "")).lower():
            continue
        if year and not str(facts.get("start_date") or facts.get("date") or "").startswith(year):
            continue
        out.append(doc)
        if len(out) >= max(1, min(int(limit), 500)):
            break
    if full:
        for doc in out:
            r = conn.execute("SELECT text, data FROM documents WHERE id=?", (doc["id"],)).fetchone()
            doc["text"], doc["data"] = r["text"], r["data"]
    return out


def get_document(conn, sha: str) -> dict | None:
    r = conn.execute("SELECT * FROM documents WHERE sha256=? OR id=?", (sha, sha if sha.isdigit() else -1)).fetchone()
    if r is None:
        return None
    return {**_as_document(r), "text": r["text"], "data": r["data"]}


def _sources(conn) -> Iterator[tuple[str, str, str, str]]:
    for r in conn.execute("SELECT id, name, text, facts FROM documents"):
        facts = json.loads(r["facts"]) if r["facts"] else {}
        summary = " ".join(str(facts.get(k) or "") for k in ("title", "summary", "party", "reference", "place")).strip()
        yield f"d{r['id']}", "document", r["name"], (summary + " " + r["text"]).strip()


def passages(conn, question: str, limit: int = 6, alternatives: list[str] | None = None) -> list[dict]:
    """The best passages for a question across every document, each with where it came from."""
    return rag.retrieve(conn, question, limit, alternatives, sources=_sources)


def counts(conn) -> dict[str, Any]:
    r = conn.execute("SELECT COUNT(*) AS n, SUM(judged=0) AS waiting, SUM(judged=1) AS read, SUM(judged=2) AS skipped FROM documents").fetchone()
    return {"documents": r["n"], "waiting": r["waiting"] or 0, "read": r["read"] or 0, "skipped": r["skipped"] or 0}


def by_kind(conn) -> list[dict]:
    """How many documents of each recognised kind there are."""
    tally: Counter[str] = Counter()
    for r in conn.execute("SELECT facts FROM documents WHERE judged=1 AND facts<>''"):
        tally[json.loads(r["facts"]).get("kind", "other")] += 1
    return [{"kind": k, "count": n} for k, n in tally.most_common()]
