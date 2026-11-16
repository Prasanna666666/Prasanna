"""The one store of everything that was read: every file and every mail, once, with what it is and what it says.

The sealed reader (parser.py, no network) turns files into plain JSON; this module takes that JSON into the encrypted database, deletes the readable
copy, and has the local model say what each document is. Code verifies every amount and every date against the document's own text (extract.py).
Other apps (Finance today; Health, Travel and others later) do not read files themselves: they ask this store for the kinds of documents that are relevant to them.

A document is judged once: read by the model (`judged = 1`), or not worth the model's time (`judged = 2`, a newsletter). Either way it gets a `ready`
number, so an app that asks "what is new since number N?" never misses a document that was judged after a later one arrived.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sqlite3
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kit import extract, rag
from kit.module import Module

from . import apps, limits, relevance

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
    """
    CREATE TABLE pending_changes (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,                      -- move | albums | delete | export | file_move | file_copy
        label TEXT NOT NULL,
        dest TEXT NOT NULL,
        entries TEXT NOT NULL,                   -- [[item id, from, to, size, modified]], what would happen and what each file looked like when it was prepared
        nonce TEXT NOT NULL,                     -- given only to the confirmation window when it is opened
        created REAL NOT NULL,
        viewed REAL,                             -- when the window was opened: nothing is confirmed without having been looked at
        status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | cancelled | failed
        decided REAL,
        batch TEXT,                              -- the journal number a done move can be undone with
        result TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE write_audit (
        id INTEGER PRIMARY KEY,
        at REAL NOT NULL,
        change_id TEXT NOT NULL,
        action TEXT NOT NULL,                    -- prepared | opened | confirmed | refused | cancelled | undone
        detail TEXT NOT NULL DEFAULT ''
    );
    """,
    """
    CREATE TABLE file_moves (
        id INTEGER PRIMARY KEY,
        batch TEXT NOT NULL,                     -- the journal number a filing can be undone with
        src TEXT NOT NULL,
        dst TEXT NOT NULL,
        op TEXT NOT NULL,                        -- file_move | file_copy
        status TEXT NOT NULL,                    -- pending (written before the file is touched) | done | failed | undone
        at REAL NOT NULL
    );
    CREATE INDEX file_moves_batch ON file_moves (batch);
    """,
    """
    ALTER TABLE documents ADD COLUMN fact_kind TEXT;   -- the kind the model gave (invoice, ticket ...), kept apart so counting and listing by kind never read every document
    UPDATE documents SET fact_kind=json_extract(facts,'$.kind') WHERE facts<>'';
    CREATE INDEX documents_fact_kind ON documents (judged, fact_kind);
    CREATE INDEX documents_area ON documents (area);
    CREATE TRIGGER documents_kind_new AFTER INSERT ON documents WHEN NEW.facts<>'' BEGIN
        UPDATE documents SET fact_kind=json_extract(NEW.facts,'$.kind') WHERE id=NEW.id;
    END;
    CREATE TRIGGER documents_kind_changed AFTER UPDATE OF facts ON documents BEGIN
        UPDATE documents SET fact_kind=CASE WHEN NEW.facts<>'' THEN json_extract(NEW.facts,'$.kind') END WHERE id=NEW.id;
    END;
    """,
    """
    CREATE TABLE trip_items (
        id INTEGER PRIMARY KEY,
        trip TEXT NOT NULL,                      -- which trip (a short key from its place and first day)
        section TEXT NOT NULL DEFAULT '',        -- Documents, Money, Clothes ...
        text TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,         -- 1 = packed
        pos INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX trip_items_trip ON trip_items (trip);
    """,
    """
    ALTER TABLE documents ADD COLUMN source TEXT NOT NULL DEFAULT '';   -- where the file lay (folder and path), so a newer version of the same file replaces the older one
    CREATE INDEX documents_source ON documents (source) WHERE source <> '';
    """,
    """
    CREATE TABLE cases (
        id INTEGER PRIMARY KEY,
        input_hash TEXT NOT NULL UNIQUE,         -- which pieces, as they were when it was read: a changed matter is read again
        members TEXT NOT NULL,                   -- the ids of its pieces
        summary TEXT NOT NULL DEFAULT '',        -- what was understood of it as a whole, every claim with a quote ('' = not yet)
        tries INTEGER NOT NULL DEFAULT 0
    );
    ALTER TABLE documents ADD COLUMN case_id INTEGER;
    CREATE INDEX documents_case ON documents (case_id);
    """,
    """
    CREATE TABLE links (
        sha_a TEXT NOT NULL,                     -- two pieces (by content) and whether reading them showed they are one matter
        sha_b TEXT NOT NULL,
        same INTEGER NOT NULL,
        PRIMARY KEY (sha_a, sha_b)
    );
    """,
    """
    CREATE TABLE trace (
        id INTEGER PRIMARY KEY,
        run TEXT NOT NULL,                       -- which read (when it started)
        at TEXT NOT NULL,
        name TEXT NOT NULL,                      -- the file
        step TEXT NOT NULL,                      -- what was done to it
        detail TEXT NOT NULL DEFAULT '',         -- what came of it (never what the file says)
        seconds REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX trace_run ON trace (run, id);
    """,
    """
    ALTER TABLE cases ADD COLUMN rank INTEGER NOT NULL DEFAULT 99;   -- where its files' app comes in the order the apps are served in (see priority)
    CREATE INDEX cases_rank ON cases (rank, id);
    """,
    """
    ALTER TABLE documents ADD COLUMN tries INTEGER NOT NULL DEFAULT 0;   -- how many times the model has been given the file without a usable answer
    """,
    """
    ALTER TABLE documents ADD COLUMN fact_apps TEXT;   -- '|finance|health|': the apps the model marked the file for, kept apart so listing by app never reads every document
    -- Files sorted before the apps were declared have no marks yet; `mark_old_files` gives them theirs from the words the apps declare (nothing is matched here).
    UPDATE documents SET fact_apps = '|' || COALESCE((SELECT group_concat(value, '|') FROM json_each(json_extract(facts, '$.apps'))), '') || '|' WHERE facts<>'' AND json_valid(facts);
    CREATE INDEX documents_fact_apps ON documents (judged, fact_apps);
    CREATE TRIGGER documents_apps_new AFTER INSERT ON documents WHEN NEW.facts<>'' AND json_valid(NEW.facts) BEGIN
        UPDATE documents SET fact_apps = '|' || COALESCE((SELECT group_concat(value, '|') FROM json_each(json_extract(NEW.facts, '$.apps'))), '') || '|' WHERE id=NEW.id;
    END;
    CREATE TRIGGER documents_apps_changed AFTER UPDATE OF facts ON documents BEGIN
        UPDATE documents SET fact_apps = CASE WHEN NEW.facts<>'' AND json_valid(NEW.facts)
            THEN '|' || COALESCE((SELECT group_concat(value, '|') FROM json_each(json_extract(NEW.facts, '$.apps'))), '') || '|' END WHERE id=NEW.id;
    END;
    """,
    """
    ALTER TABLE documents ADD COLUMN promised INTEGER NOT NULL DEFAULT 0;   -- for a mail: how many attachments it says it carried (so the number of documents in mails is known before they are all taken out)
    """,
    """
    ALTER TABLE documents ADD COLUMN sig TEXT;   -- (not used any more)
    CREATE TABLE sigs (doc_id INTEGER NOT NULL, band INTEGER NOT NULL, h INTEGER NOT NULL);
    CREATE INDEX sigs_lookup ON sigs (band, h);
    """,
    """
    CREATE TABLE kind_names (kind TEXT PRIMARY KEY, name TEXT NOT NULL);   -- the plain name the model gave to each name it had given files: "Bank statement (Dutch)" and "Rekeningafschrift" become "bank statement"
    """,
    """
    CREATE TABLE IF NOT EXISTS kind_concepts (kind TEXT PRIMARY KEY, concept TEXT NOT NULL);   -- what a plain kind means to the part that shows it (see concepts)
    """,
)
MODULE = Module("library", MIGRATIONS)
FILE_KINDS = {"text", "csv", "pdf", "image", "sheet", "doc", "html", "email", "json", "binary"}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COLLECTION = re.compile(r"^[a-z]{2,20}$")
Progress = Callable[[str], None]


JUDGED_FAILED = 3  # judged = 3: the model could not make sense of it yet


def _kept(value: str, limit: str, what: str, cut: list[str]) -> str:
    """The value, cut to the limit named in limits.json; when it was cut, `what` is added to `cut` so the document says it was read with something left out (and is read again when the limit changes)."""
    most = limits.get(limit)
    if len(value) <= most:
        return value
    cut.append(what)
    return value[:most]


def _valid(d: Any, stem: str) -> bool:
    return bool(
        isinstance(d, dict)
        and d.get("schema") == 1
        and isinstance(d.get("sha256"), str)
        and _SHA.match(d["sha256"])
        and stem == d["sha256"]
        and d.get("kind") in FILE_KINDS
        and isinstance(d.get("name"), str)
        and 0 < len(d["name"]) <= limits.get("max_name_chars")
        and isinstance(d.get("text"), str)
        and len(d["text"]) <= limits.get("max_text_chars")
        and (d.get("source") is None or (isinstance(d["source"], str) and len(d["source"]) <= limits.get("max_source_chars")))
    )


def _promised(d: dict) -> int:
    meta = d.get("meta") if d.get("kind") == "email" and isinstance(d.get("meta"), dict) else {}
    count = (meta or {}).get("attachments")
    return count if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= limits.get("max_promised_attachments") else 0


def _structured(d: dict) -> str:
    keep = {
        k: d["data"][k]
        for k in ("rows", "lines", "table", "table_pdfplumber", "table_poppler")
        if isinstance(d.get("data"), dict) and isinstance(d["data"].get(k), list)
    }
    if isinstance(d.get("meta"), dict) and d["meta"]:
        keep["meta"] = d["meta"]  # how it was read: scanned, how confident, how many pages
    return json.dumps(keep) if keep else ""


def _replace_older_versions(conn, directory: Path, source: str, sha: str) -> int:
    """The same file, changed: the older versions go (what they said is no longer what the file says), and the reader forgets it has read them, so going back to
    that content later reads it again. The original file is not touched; this is only the stored text."""
    old = [r[0] for r in conn.execute("SELECT sha256 FROM documents WHERE source=? AND sha256<>?", (source, sha))]
    for digest in old:
        conn.execute("DELETE FROM documents WHERE sha256=?", (digest,))
        with contextlib.suppress(OSError):
            (directory / ".done" / digest).unlink(missing_ok=True)
    return len(old)


def _forget(conn, directory: Path, where: str, args: tuple = ()) -> int:
    """Forget the documents that match `where`, so that they are read again. What is forgotten is a copy the reader can make again: nothing in your mail or your folders is touched.
    Groups that included a forgotten file are dropped, to be made again from what remains."""
    rows = conn.execute(f"SELECT id, sha256 FROM documents WHERE {where}", args).fetchall()
    gone = {r["id"] for r in rows}
    for r in rows:
        with contextlib.suppress(OSError):
            (directory / ".done" / r["sha256"]).unlink(missing_ok=True)
    conn.execute(f"DELETE FROM documents WHERE {where}", args)
    for case in conn.execute("SELECT id, members FROM cases").fetchall():
        try:
            members = set(json.loads(case["members"]))
        except (ValueError, TypeError):
            members = set()
        if members & gone:
            conn.execute("DELETE FROM cases WHERE id=?", (case["id"],))
    conn.commit()
    for name in (".mailseen-2", ".seen-2", ".attached-2"):  # what the reader remembers of having read mail
        shutil.rmtree(directory / name, ignore_errors=True)
    return len(rows)


def forget_mail(conn, directory: Path) -> int:
    """Forget every mail (and what was taken out of it) that is held here, so that mail is read again, from the mailboxes now chosen only."""
    return _forget(conn, directory, "area='mail'")


def forget_stale_reads(conn, directory: Path, better_engine: str = "") -> int:
    """Forget what was read with something left out under limits that have since changed (each document records the version of the limits it was read under and which of them cut it),
    and, when a better text recognition is available (`better_engine`), the scanned documents that were read with another one: they are read again, whole. Nothing is named in code:
    change `limits.json`, or start the better engine, and this finds them."""
    where = (
        "(json_valid(data) AND json_array_length(COALESCE(json_extract(data, '$.meta.limits_hit'), '[]')) > 0 AND COALESCE(json_extract(data, '$.meta.limits_version'), '') <> ?)"
        " OR (json_valid(data) AND json_extract(data, '$.meta.limits_version') IS NULL AND (json_extract(data, '$.meta.ocr_cut_short') = 1 OR length(text) >= 1990000))"
    )
    args: tuple = (limits.version(),)
    if better_engine:
        where += " OR (json_valid(data) AND json_extract(data, '$.meta.ocr_pages') > 0 AND length(text) >= 80 AND COALESCE(json_extract(data, '$.meta.ocr_engine'), '') <> ?)"  # only where the old reader found real text: a logo with no words gains nothing
        args += (better_engine,)
    return _forget(conn, directory, where, args)


def _repaired(d: Any, stem: str) -> dict | None:
    """A result the reader wrote that is not quite in the form Atlas keeps is put right, not refused: no name, a name or a location that is too long, a kind Atlas has no word for, too much
    text, a version of the form it does not know. Only a result that is not a result at all (or whose file name is not a content identifier) cannot be put right."""
    if not isinstance(d, dict) or not _SHA.match(stem):
        return None
    fixed = dict(d)
    fixed["schema"], fixed["sha256"] = 1, stem
    given_name = fixed.get("name")
    name = given_name if isinstance(given_name, str) else ""
    cut: list[str] = []
    fixed["name"] = _kept(name.strip() or f"unnamed file {stem[:8]}", "max_name_chars", "name", cut)
    if fixed.get("kind") not in FILE_KINDS:
        fixed["kind"] = "binary"
    given_text = fixed.get("text")
    fixed["text"] = _kept(given_text if isinstance(given_text, str) else "", "max_text_chars", "text", cut)
    source = fixed.get("source")
    if isinstance(source, str):
        fixed["source"] = _kept(source, "max_source_chars", "source", cut)
    elif source is not None:
        fixed["source"] = None
    if cut:
        given_meta = fixed.get("meta")
        meta = given_meta if isinstance(given_meta, dict) else {}
        fixed["meta"] = {**meta, "limits_hit": [*meta.get("limits_hit", []), *cut], "limits_version": limits.version()}
    return fixed if _valid(fixed, stem) else None


def _why_rejected(f: Path, d: Any, error: Exception | None = None) -> tuple[str, str, str]:
    """For a result the service would not take in: its name, the exact reason in plain words, and which count it belongs to (documents, mails, attachments)."""
    named = isinstance(d, dict) and isinstance(d.get("name"), str) and d["name"].strip()
    name = d["name"][:120] if named else f.stem[:20]
    checks = (
        (isinstance(error, UnicodeDecodeError), "the result of reading it contained characters that could not be decoded"),
        (isinstance(error, json.JSONDecodeError), "the result of reading it was damaged"),
        (not isinstance(d, dict), "the result of reading it was not in the form Atlas expects"),
        (isinstance(d, dict) and d.get("schema") != 1, "it was read by a version of the reader that Atlas does not know"),
        (isinstance(d, dict) and not named, "it has no name"),
        (isinstance(d, dict) and isinstance(d.get("name"), str) and len(d["name"]) > limits.get("max_name_chars"), "its name is too long"),
        (
            isinstance(d, dict) and not (isinstance(d.get("sha256"), str) and _SHA.match(d["sha256"]) and f.stem == d["sha256"]),
            "its identifier does not match its content",
        ),
        (isinstance(d, dict) and d.get("kind") not in FILE_KINDS, "a kind of file Atlas does not keep"),
        (isinstance(d, dict) and not isinstance(d.get("text"), str), "it has no readable text"),
        (isinstance(d, dict) and isinstance(d.get("text"), str) and len(d["text"]) > limits.get("max_text_chars"), "too much text to keep"),
        (isinstance(d, dict) and isinstance(d.get("source"), str) and len(d["source"]) > limits.get("max_source_chars"), "its location is too long to record"),
    )
    reason = next((why for failed, why in checks if failed), "the result of reading it could not be used")
    area = d.get("area") if isinstance(d, dict) else ""
    group = ("mails" if isinstance(d, dict) and d.get("kind") == "email" else "attachments") if area == "mail" else "documents"
    return name, reason, group


def ingest_dir(
    conn, directory: Path, stop=None, on_new: Callable[[str], None] | None = None, on_rejected: Callable[[str, str, str], None] | None = None
) -> dict[str, int]:
    """Take the reader's output into the database. Strict: anything unexpected is skipped, never partially trusted. The readable copy is deleted once stored."""
    new = known = rejected = replaced = 0
    stored: list[Path] = []
    for looked, f in enumerate(sorted(directory.resolve().glob("*.json")), 1):
        if stop is not None and looked % 100 == 0 and stop():
            break  # Stop: what is taken in so far stays, the rest waits for the next read
        d = None
        try:
            if f.is_symlink() or f.stat().st_size > limits.get("max_json_bytes"):
                raise ValueError("symlink or too large")
            raw = json.loads(f.read_text(encoding="utf-8"))
            d = _repaired(raw, f.stem)
            if d is None:
                raise ValueError("schema")
        except FileNotFoundError:
            continue  # taken away while it was being looked at: it is looked at again next time
        except (ValueError, OSError) as error:
            rejected += 1
            with contextlib.suppress(
                OSError
            ):  # a result that cannot be used at all is removed with its mark, so the reader reads the file again at the next round
                f.unlink()
                (directory / ".done" / f.stem).unlink(missing_ok=True)
            if on_rejected is not None:
                on_rejected(*_why_rejected(f, locals().get("raw"), error))
            continue
        area = d["area"] if isinstance(d.get("area"), str) and (d["area"] == "mail" or _COLLECTION.match(d["area"])) else ""
        source = d.get("source") or ""
        cur = conn.execute(
            "INSERT OR IGNORE INTO documents (sha256, name, kind, text, area, data, parsed_at, source, promised) VALUES (?,?,?,?,?,?,?,?,?)",
            (d["sha256"], d["name"], d["kind"], d["text"], area, _structured(d), str(d.get("parsed_at", ""))[:25], source, _promised(d)),
        )
        if cur.rowcount and source:
            replaced += _replace_older_versions(conn, directory, source, d["sha256"])
        new += cur.rowcount
        known += 1 - cur.rowcount
        if cur.rowcount and on_new is not None:
            on_new(d["name"])
        stored.append(f)
    conn.commit()
    if os.access(directory, os.W_OK):
        for f in stored:  # the text now lives only in the encrypted database
            f.unlink(missing_ok=True)
    return {"new": new, "known": known, "rejected": rejected, "replaced": replaced}


# ---- asking: what any app can take -------------------------------------------------------------------------------------------
GENTLE_SECONDS = float(os.environ.get("LIBRARY_GENTLE_SECONDS", "0"))
LIST_COLUMNS = "id, sha256, name, kind, area, parsed_at, facts, ready, case_id"


# ---- Health: medical documents are recognised by kind or by the health folder


def proper_name(facts: dict, file_name: str, kind: str = "") -> str:
    """What a document is called on screen: its own title with who it is from, taken from what it says, never the file name it happens to have. A file name is the last resort."""
    title = str(facts.get("title") or "").strip()
    party = str(facts.get("party") or "").strip()
    what = kind.replace("_", " ").capitalize() if kind and kind != "other" else ""
    if title and party and party.casefold() not in title.casefold():
        return f"{title} · {party}"
    return title or " · ".join(x for x in (what, party) if x) or file_name


def _as_document(r) -> dict[str, Any]:
    facts = json.loads(r["facts"]) if r["facts"] else {}
    doc: dict[str, Any] = {
        "id": r["id"],
        "sha256": r["sha256"],
        "name": r["name"],
        "title": proper_name(facts, r["name"], facts.get("kind", "")),
        "file_kind": r["kind"],
        "area": r["area"],
        "kind": facts.get("kind", ""),
        "apps": facts.get("apps") or [],
        "facts": facts,
        "ready": r["ready"],
    }
    doc["understood"] = r["case_id"] is not None  # read together with everything that belongs with it (see casebook)
    return doc


def held_back(conn, area: str = "", kinds: list[str] | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """The documents that are not shown yet, each with the plain reason: waiting for the model, not understood after two tries, or still being read together with what belongs with it."""
    wanted = set(kinds or [])
    out: list[dict[str, Any]] = []
    for r in conn.execute(
        "SELECT id, name, kind, area, facts, judged, case_id FROM documents WHERE judged IN (0, 1, 3) AND kind<>'email' AND TRIM(text)<>'' ORDER BY id DESC"
    ):
        facts = json.loads(r["facts"]) if r["facts"] else {}
        if area and r["area"] != area and facts.get("kind") not in wanted:
            continue
        if r["judged"] == 0:
            why = "waiting for the model"
        elif r["judged"] == JUDGED_FAILED:
            why = "the model could not make sense of it yet"
        elif r["case_id"] is None:
            why = "being read together with everything that belongs with it"
        else:
            continue
        out.append({"id": r["id"], "title": proper_name(facts, r["name"], facts.get("kind", "")), "why": why})
        if len(out) >= limit:
            break
    return out


def _fits(doc: dict[str, Any], wanted: set[str], area: str, source: str, only_understood: bool, app: str = "") -> bool:
    """Does this document belong in the list that was asked for?"""
    said = any(w in doc["kind"].lower() for w in wanted)  # the words asked for, in what the model called the file
    if (only_understood or source == "documents") and not doc["understood"]:
        return False  # shown only when understood completely enough to help (the rest is listed by `held_back`, with the reason)
    if source == "documents":
        if doc["file_kind"] == "email":
            return False  # documents from folders and the documents inside emails, never a whole email
    elif source and (doc["area"] == "mail") != (source == "mail"):  # `mail` only the mail; `files` everything else
        return False
    if wanted or area or app:
        return said or bool(app and app in doc["apps"]) or bool(area and doc["area"] == area)
    return bool(doc["apps"])  # everything the model found to be about some app


@dataclass(frozen=True)
class Narrow:
    """What narrows a list of documents besides their kinds: the `area` they came from, the `place` and `year` they are about, only those newer than number `since`, only `source`
    "documents" (never a whole email), only the ones already `only_understood`, and the `app` the model marked them for."""

    area: str = ""
    place: str = ""
    year: str = ""
    since: int = 0
    source: str = ""
    only_understood: bool = False
    app: str = ""


def list_documents(conn, kinds: list[str] | None = None, narrow: Narrow | None = None, limit: int = 100, full: bool = False) -> list[dict]:
    """Ready documents, oldest first. `app` is an app the model marked the file for; `kinds` are words looked for in what the model called the file; with `area`, a document also
    qualifies when it came from that area. Without any of them, everything the model found to be about some app is returned. With `full`, the text and structured data come too."""
    n = narrow or Narrow()
    area, place, year, since, source, only_understood, app = n.area, n.place, n.year, n.since, n.source, n.only_understood, n.app
    wanted = {k.lower() for k in kinds or [] if k}
    out: list[dict] = []
    names = kind_names(conn)
    where = "ready > ?"
    args: list[Any] = [max(0, int(since))]
    # the database narrows the list before any document is looked at (the same conditions as `_fits`): without this a big library is read row by row for every page asked for
    either: list[str] = []
    if wanted:
        either += ["LOWER(COALESCE(fact_kind, '')) LIKE ?" for _ in wanted]
        args += [f"%{w}%" for w in sorted(wanted)]
    if app:
        either.append("fact_apps LIKE ?")
        args.append(f"%|{app}|%")
    if area:
        either.append("area=?")
        args.append(area)
    if either:
        where += " AND (" + " OR ".join(either) + ")"
    else:
        where += " AND COALESCE(fact_apps, '||') NOT IN ('||', '')"  # everything the model found to be about some app
    if only_understood or source == "documents":
        where += " AND case_id IS NOT NULL"
    if source == "documents":
        where += " AND kind<>'email'"
    for r in conn.execute(f"SELECT {LIST_COLUMNS} FROM documents WHERE {where} ORDER BY ready", args):
        doc = _as_document(r)
        if not _fits(doc, wanted, area, source, only_understood, app):
            continue
        facts = doc["facts"]
        if place and place.lower() not in str(facts.get("place", "")).lower():
            continue
        if year and not str(facts.get("start_date") or facts.get("date") or "").startswith(year):
            continue
        plain = names.get(_kind_key(doc["kind"]))
        if plain:  # the apps see the plain name (and not every wording and language the model used)
            doc["kind_given"], doc["kind"], doc["facts"] = doc["kind"], plain, {**doc["facts"], "kind": plain}
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
    for r in conn.execute("SELECT id, name, text, facts, area FROM documents"):
        facts = json.loads(r["facts"]) if r["facts"] else {}
        summary = " ".join(str(facts.get(k) or "") for k in ("title", "summary", "party", "reference", "place")).strip()
        yield f"d{r['id']}", "document", proper_name(facts, r["name"], facts.get("kind", "")), (summary + " " + r["text"]).strip()


def _fingerprint(conn, more_sources=None) -> str:
    """Changes whenever something searchable changed (a document arrived or was judged, pictures gained text): the search checks nothing else."""
    r = conn.execute("SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(SUM(judged),0), COALESCE(MAX(ready),0) FROM documents").fetchone()
    more = getattr(more_sources, "fingerprint", None)
    return f"{tuple(r)}|{more() if more else ''}"


_INDEXING = threading.Lock()


def warm_search(conn, more_sources=None, stop=None) -> int:
    """Bring the search index up to date now, in the background of whatever else is going on, so no question ever waits for it. Returns how many items were indexed."""
    if not _INDEXING.acquire(blocking=False):
        return 0  # already being done
    try:
        return rag.reindex(conn, _all_sources(more_sources), _fingerprint(conn, more_sources), stop)
    finally:
        _INDEXING.release()


def _all_sources(more_sources=None):
    def sources(c):
        yield from _sources(c)
        if more_sources is not None:
            yield from more_sources(c)

    return sources


def passages(conn, question: str, limit: int = 6, alternatives: list[str] | None = None, more_sources=None) -> list[dict]:
    """The best passages for a question across every document, each with where it came from. `more_sources` adds more sources (the text found in pictures).
    The index is normally already up to date (it is kept so in the background); if it is being brought up to date right now, the question uses what is there."""
    sources, fingerprint = _all_sources(more_sources), _fingerprint(conn, more_sources)
    if _INDEXING.acquire(blocking=False):
        try:
            return rag.retrieve(conn, question, limit, alternatives, sources=sources, fingerprint=fingerprint)
        finally:
            _INDEXING.release()
    return rag.retrieve(conn, question, limit, alternatives, sources=sources, fingerprint=fingerprint, refresh=False)


def counts(conn) -> dict[str, Any]:
    r = conn.execute(
        "SELECT COUNT(*) AS n, SUM(judged=0) AS waiting, SUM(judged=1) AS read, SUM(judged=2) AS skipped, SUM(judged=3) AS unclear FROM documents"
    ).fetchone()
    return {"documents": r["n"], "waiting": r["waiting"] or 0, "read": r["read"] or 0, "skipped": r["skipped"] or 0, "unclear": r["unclear"] or 0}


def forget(conn, doc_id: int) -> str | None:
    """Atlas stops keeping what it read from one document (the original file is never touched). The reader remembers it has read that content, so it is not read again
    unless the file itself changes. Returns the document's name, or None when there is no such document."""
    row = conn.execute("SELECT name FROM documents WHERE id=?", (doc_id,)).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    return str(row["name"])


MAX_TRIES = (
    3  # a file the model gave no usable answer for this many times is not asked again until the file itself changes (each try can be several model calls)
)


def retry_unclear(conn) -> int:
    """Files the model could not make sense of get another try when the person presses Read new files, up to MAX_TRIES times in all."""
    n = conn.execute("UPDATE documents SET judged=0 WHERE judged=3 AND tries<?", (MAX_TRIES,)).rowcount
    conn.commit()
    return n


def by_kind(conn) -> list[dict]:
    """How many documents of each recognised kind there are."""
    out = [
        {"kind": r[0] or "other", "count": r[1]}
        for r in conn.execute("SELECT fact_kind, COUNT(*) FROM documents WHERE judged=1 AND fact_kind IS NOT NULL GROUP BY fact_kind ORDER BY COUNT(*) DESC")
    ]
    return out


def ingest_pictures(conn, engine_conn) -> int:
    """Pictures in the photo folder that have readable text (a receipt, a letter, a ticket) become documents, so they are judged, searched and used for
    bills like any file. The text is what the picture engine already read; nothing is read twice. Returns how many were added."""
    import hashlib

    added = 0
    rows = engine_conn.execute(
        "SELECT i.rel_path AS name, f.text AS text FROM items i JOIN fts f ON f.rowid=i.id "
        "WHERE i.missing=0 AND i.kind='image' AND length(f.text) >= ? AND i.rel_path NOT LIKE 'Inbox/%' AND i.rel_path NOT LIKE 'MailPictures/%'",
        (relevance.MIN_TEXT,),
    ).fetchall()
    for r in rows:
        sha = hashlib.sha256(f"picture\0{r['name']}\0{r['text']}".encode()).hexdigest()
        cur = conn.execute(
            "INSERT OR IGNORE INTO documents (sha256, name, kind, text, area, data, parsed_at) VALUES (?,?,?,?,?,?,?)",
            (sha, str(r["name"])[: limits.get("max_name_chars")], "image", str(r["text"])[: limits.get("max_text_chars")], "pictures", "", ""),
        )
        added += cur.rowcount
    conn.commit()
    return added


def category_suggestions(conn, threshold: int | None = None) -> list[dict[str, Any]]:
    """The kinds of file the model found that are about none of the apps and are many enough to deserve an app: [{kind, count, examples}], the biggest first."""
    limit = threshold if threshold is not None else apps.threshold()
    rows = conn.execute(
        "SELECT LOWER(TRIM(fact_kind)) AS kind, COUNT(*) AS n FROM documents WHERE judged=1 AND TRIM(COALESCE(fact_kind, ''))<>'' AND COALESCE(fact_apps, '||') IN ('||', '') "
        "GROUP BY LOWER(TRIM(fact_kind)) HAVING n>? ORDER BY n DESC LIMIT 20",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        names = [e["name"] for e in conn.execute("SELECT name FROM documents WHERE judged=1 AND LOWER(TRIM(fact_kind))=? ORDER BY id LIMIT 3", (r["kind"],))]
        out.append({"kind": r["kind"], "count": r["n"], "examples": names})
    return out


def create_app_for_kind(conn, kind: str) -> dict[str, Any]:
    """Make an app for a kind of file: its name and words come from the kind, and the files of that kind that are about no app are marked for it. The model marks new files for it from now on."""
    kind = " ".join(kind.lower().split())[:60]
    name = re.sub(r"[^a-z0-9]+", "-", kind).strip("-")[:30]
    if not kind or not name:
        return {"ok": False, "error": "that is not a kind"}
    if name in apps.names():
        return {"ok": False, "error": "there is an app with that name already"}
    apps.add_user_app(name, f"{kind}: files like these", kind)
    marked = conn.execute(
        "UPDATE documents SET facts=json_set(facts, '$.apps', json(?)) WHERE judged=1 AND LOWER(TRIM(COALESCE(fact_kind, '')))=? AND COALESCE(fact_apps, '||') IN ('||', '')",
        (json.dumps([name]), kind),
    ).rowcount
    conn.commit()
    return {"ok": True, "app": name, "files": marked}


KIND_NAMES_PROMPT = (
    "These are names that were given to files, in several languages and wordings. Give each one a short plain name (one to three words, English, lower case) so that names that mean the "
    "same thing get exactly the same plain name. Reuse a plain name from the list of existing ones whenever it fits. Answer with each name unchanged and its plain name."
)
KIND_NAMES_SCHEMA = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {"type": "object", "properties": {"given": {"type": "string"}, "plain": {"type": "string"}}, "required": ["given", "plain"]},
        }
    },
    "required": ["names"],
}
KIND_BATCH = 40


def _kind_key(kind: str) -> str:
    return " ".join(kind.lower().split())


def kind_names(conn) -> dict[str, str]:
    """The plain name of each kind the model gave (what the apps show instead of every wording and language)."""
    try:
        return {r["kind"]: r["name"] for r in conn.execute("SELECT kind, name FROM kind_names")}
    except sqlite3.OperationalError:
        return {}


def name_kinds(conn, client, model, control: Callable[[], str] | None = None) -> int:
    """Give the kinds the model has used plain names, so the apps show a few categories and not every wording: the model merges names that mean the same, reusing plain names that
    exist. A file whose name changed is handed to the apps again, so they show the new name. Returns how many kinds were named."""
    known = kind_names(conn)
    todo = [
        r["kind"]
        for r in conn.execute(
            "SELECT LOWER(TRIM(fact_kind)) AS kind FROM documents WHERE judged=1 AND TRIM(COALESCE(fact_kind, ''))<>'' GROUP BY LOWER(TRIM(fact_kind)) ORDER BY COUNT(*) DESC"
        )
        if _kind_key(r["kind"]) not in known
    ]
    named = 0
    for i in range(0, len(todo), KIND_BATCH):
        if control is not None and control() == "stop":
            break
        batch = todo[i : i + KIND_BATCH]
        existing = sorted(set(known.values()))[:80]
        try:
            data = extract._ask(
                client,
                model,
                KIND_NAMES_PROMPT,
                "Existing plain names: " + "; ".join(existing) + "\n\nNames to give a plain name:\n" + "\n".join(batch),
                KIND_NAMES_SCHEMA,
            )
        except extract.Unclear:
            data = {"names": []}
        given = {_kind_key(str(n.get("given", ""))): _kind_key(str(n.get("plain", ""))) for n in data.get("names", []) if isinstance(n, dict)}
        for kind in batch:
            plain = given.get(_kind_key(kind)) or _kind_key(kind)  # a name the model did not answer for keeps its own wording
            conn.execute("INSERT OR REPLACE INTO kind_names (kind, name) VALUES (?,?)", (_kind_key(kind), plain[:40]))
            known[_kind_key(kind)] = plain[:40]
            named += 1
    if named:
        top = conn.execute("SELECT COALESCE(MAX(ready), 0) FROM documents").fetchone()[0]
        conn.execute(
            "UPDATE documents SET ready = ready + ? WHERE judged=1 AND ready > 0 AND TRIM(COALESCE(fact_kind, ''))<>''", (top,)
        )  # handed to the apps again, with the plain names
    conn.commit()
    return named
