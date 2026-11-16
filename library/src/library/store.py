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
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from kit import extract, rag
from kit.module import Module

from . import apps, casebook, priority, recognise, relevance, similar
from .trace import FAILED, Trace

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
    ALTER TABLE documents ADD COLUMN sig TEXT;   -- a fingerprint of the words of a document the model found to be about none of the apps (see similar)
    CREATE TABLE sigs (doc_id INTEGER NOT NULL, band INTEGER NOT NULL, h INTEGER NOT NULL);
    CREATE INDEX sigs_lookup ON sigs (band, h);
    """,
)
MODULE = Module("library", MIGRATIONS)
FILE_KINDS = {"text", "csv", "pdf", "image", "sheet", "doc", "html", "email", "json", "binary"}
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
        and (d.get("source") is None or (isinstance(d["source"], str) and len(d["source"]) <= 600))
    )


def _promised(d: dict) -> int:
    meta = d.get("meta") if d.get("kind") == "email" and isinstance(d.get("meta"), dict) else {}
    count = (meta or {}).get("attachments")
    return count if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 10_000 else 0


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


def _forget(conn, directory: Path, where: str) -> int:
    """Forget the documents that match `where`, so that they are read again. What is forgotten is a copy the reader can make again: nothing in your mail or your folders is touched.
    Groups that included a forgotten file are dropped, to be made again from what remains."""
    rows = conn.execute(f"SELECT id, sha256 FROM documents WHERE {where}").fetchall()
    gone = {r["id"] for r in rows}
    for r in rows:
        with contextlib.suppress(OSError):
            (directory / ".done" / r["sha256"]).unlink(missing_ok=True)
    conn.execute(f"DELETE FROM documents WHERE {where}")
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


def forget_scanned(conn, directory: Path) -> int:
    """Forget the documents that were read from scanned pages, so that they are read again with a better text recognition. Everything else is kept."""
    return _forget(conn, directory, "json_valid(data) AND json_extract(data, '$.meta.ocr_pages') > 0")


def ingest_dir(conn, directory: Path, stop=None, on_new: Callable[[str], None] | None = None) -> dict[str, int]:
    """Take the reader's output into the database. Strict: anything unexpected is skipped, never partially trusted. The readable copy is deleted once stored."""
    new = known = rejected = replaced = 0
    stored: list[Path] = []
    for looked, f in enumerate(sorted(directory.resolve().glob("*.json")), 1):
        if stop is not None and looked % 100 == 0 and stop():
            break  # Stop: what is taken in so far stays, the rest waits for the next read
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


# ---- judging: what is each document? ------------------------------------------------------------------------------------------
MAIL_KEPT_CHARS = 600  # what is kept of an email: what it says, never what it is


def _mail_summary(facts: dict | None) -> str:
    parts = (str((facts or {}).get(k) or "") for k in ("title", "summary", "party", "date", "due_date", "reference", "place"))
    return " ".join(parts).strip()[:MAIL_KEPT_CHARS]


def _mark_ready(conn, sha: str, judged: int, facts: dict | None) -> None:
    conn.execute(
        "UPDATE documents SET judged=?, facts=?, ready=(SELECT COALESCE(MAX(ready),0)+1 FROM documents) WHERE sha256=?",
        (judged, json.dumps(facts) if facts else "", sha),
    )
    # A whole email is not kept for good: it is read in full together with everything that belongs with it, and only then reduced to what it says (see forget_mail_bodies).


def forget_mail_bodies(conn) -> int:
    """Emails whose matter has been understood keep only what they say; returns how many were cut down. An email not yet read as part of its matter is kept whole."""
    done = 0
    while True:
        rows = conn.execute(
            "SELECT id, facts FROM documents WHERE area='mail' AND kind='email' AND judged>0 AND case_id IS NOT NULL AND length(text)>? LIMIT 500",
            (MAIL_KEPT_CHARS,),
        ).fetchall()
        if not rows:
            return done
        for r in rows:
            conn.execute("UPDATE documents SET text=?, data='' WHERE id=?", (_mail_summary(json.loads(r["facts"]) if r["facts"] else None), r["id"]))
        conn.commit()
        done += len(rows)


def _data(d) -> dict:
    try:
        return json.loads(d["data"]) if d["data"] else {}
    except ValueError:
        return {}


def _attachment_count(d) -> int:
    meta = _data(d).get("meta")
    count = meta.get("attachments") if isinstance(meta, dict) else 0
    return count if isinstance(count, int) else 0


def _exact_facts(d) -> dict | None:
    """Documents that need no model: a bank standard (MT940, camt.053), the ECB's exchange-rate file, or a picture with no text in it (a photo). What each is is its own plain
    label; the apps it is about are the ones whose declared words appear in that label."""
    if recognise.bank_standard(d["text"]):
        return {"kind": "bank statement", "title": "Bank statement", "apps": apps.matching("bank statement")}
    if recognise.exchange_rate_file(_data(d).get("rows")):
        return {"kind": "exchange rates", "title": "ECB exchange rates", "apps": apps.matching("ECB exchange rates")}
    if d["kind"] == "image" and len(d["text"].strip()) < relevance.MIN_TEXT:  # a picture with no text in it is a photo, not a document: Photos' business
        return {"kind": "photo", "title": d["name"], "apps": []}
    return None


JUDGE_CHUNK = 100  # documents held in memory at a time: tens of thousands of mails never sit in memory together


# The model reaches the documents that fill the dashboards first: the folders you named (health, finance, travel ...), then loose files, and the mail last.


def _pending_chunks(conn):
    """Documents not yet judged, a chunk at a time, folder documents first, then loose files, then mail."""
    for tier in priority.tiers():
        last = 0
        while True:
            rows = conn.execute(
                f"SELECT id, sha256, name, kind, text, data, area FROM documents WHERE judged=0 AND id>? AND {tier} ORDER BY id LIMIT ?", (last, JUDGE_CHUNK)
            ).fetchall()
            if not rows:
                break
            last = rows[-1]["id"]
            yield rows


def waiting_files(conn, current: str = "", limit: int = 5) -> list[str]:
    """The next files the model will identify, in the order they will be taken (named folders, then loose files, then mail); only files with text for the model."""
    names: list[str] = []
    for tier in priority.tiers():
        rows = conn.execute(f"SELECT name FROM documents WHERE judged=0 AND kind<>'binary' AND TRIM(text)<>'' AND {tier} ORDER BY id LIMIT ?", (limit + 1,))
        names += [r["name"] for r in rows if r["name"] != current]
        if len(names) >= limit:
            break
    return names[:limit]


def _wait_while_paused(conn, control: Callable[[], str] | None) -> None:
    while control is not None and control() == "pause":  # paused by the person: wait here, nothing is lost
        conn.commit()
        time.sleep(0.5)


def _understand(client, model: str, d, progress: Progress | None = None) -> dict:
    """What the model makes of one document: what it is and its key facts, and for a medical document the lab values and medicines the document itself prints."""
    declared = apps.describe()
    facts = extract.classify_short(client, model, d["name"], d["text"], declared)  # the quick question first: what is it, and which apps is it about
    if not (facts.get("apps") or d["area"] in declared):
        return facts  # about none of the apps: nothing more is asked of the model
    full = extract.classify(
        client, model, d["name"], d["text"], declared
    )  # about an app: the details that app needs (amounts, dates, parties), checked against the whole text
    facts = {**full, "apps": sorted({*full.get("apps", []), *facts.get("apps", [])})}
    readers = {
        apps.reading(name) for name in [*facts.get("apps", []), d["area"]]
    }  # an app can ask for an extra reading of its files (a folder named after the app counts too)
    if "medical" in readers:
        facts["health"] = extract.medical_details(client, model, d["name"], d["text"], progress)
    return facts


def _trace(trace: Trace | None, name: str, step: str, detail: str = "", seconds: float = 0.0) -> None:
    if trace is not None:
        trace.step(name, step, detail, seconds)


def _both(progress: Progress | None, trace: Trace | None, name: str) -> Progress:
    """The progress of one long reading (the parts of a medical document) goes to the panel and into the trace."""

    def say(message: str) -> None:
        if progress:
            progress(message)
        _trace(trace, name, "reading part", message.rsplit(": ", 1)[-1])

    return say


def _identify_one(conn, client, model, d, progress: Progress | None, trace: Trace | None, ahead: _Ahead) -> tuple[str, str]:
    """The model identifies one file and the result is saved at once (the counts in the panel change with every file, not every twentieth).
    Returns "ok", "unclear" (answered but unusable: counted and tried again at the next read) or "unreachable" with the reason."""
    _trace(trace, d["name"], "sorting", f"{len(d['text']):,} characters")
    started = time.monotonic()
    try:
        facts = ahead.result(d, _both(progress, trace, d["name"]))
    except extract.Unclear as why:
        conn.execute("UPDATE documents SET judged=3, tries=tries+1 WHERE sha256=?", (d["sha256"],))
        tries = conn.execute("SELECT tries FROM documents WHERE sha256=?", (d["sha256"],)).fetchone()[0]
        _trace(trace, d["name"], FAILED, f"{why}; it is tried again at the next read (try {tries} of {MAX_TRIES})", time.monotonic() - started)
        conn.commit()
        return "unclear", ""
    except Stopped:
        return "stopped", ""
    except RuntimeError as exc:
        return "unreachable", str(exc)
    _mark_ready(conn, d["sha256"], 1, facts)
    if not facts.get("apps") and d["kind"] != "email" and (sig := similar.signature(d["text"])):
        similar.remember(
            conn, conn.execute("SELECT id FROM documents WHERE sha256=?", (d["sha256"],)).fetchone()[0], sig
        )  # the next one that reads like it is not asked
    _trace(trace, d["name"], "sorted", f"{facts.get('kind', 'other')}", time.monotonic() - started)
    conn.commit()
    return "ok", ""


def _duration(seconds: float) -> str:
    hours, rest = divmod(int(seconds), 3600)
    return f"{hours} h {rest // 60} min" if hours else f"{rest // 60} min" if rest >= 60 else f"{rest} s"


MIN_HISTORY = 20  # files of an app that must have been looked at before its own history is trusted for the time left


def model_work_left(conn) -> int:
    """How many of the files still waiting will really go to the model. Not all do: most mail is skipped in an instant, most documents are not. So for each app the files
    waiting are counted by the share of that app's files that went to the model so far (its own history; the overall share for an app with too little history)."""
    history = {
        r["area"]: (r["sorted"] or 0, r["skipped"] or 0)
        for r in conn.execute("SELECT area, SUM(judged=1) AS sorted, SUM(judged=2) AS skipped FROM documents WHERE judged IN (1, 2) GROUP BY area")
    }
    sorted_all, skipped_all = sum(s for s, _ in history.values()), sum(k for _, k in history.values())
    overall = sorted_all / (sorted_all + skipped_all) if sorted_all + skipped_all else 1.0
    left = 0.0
    for r in conn.execute("SELECT area, COUNT(*) AS n FROM documents WHERE judged=0 AND TRIM(text)<>'' GROUP BY area"):
        done, skipped = history.get(r["area"], (0, 0))
        left += r["n"] * (done / (done + skipped) if done + skipped >= MIN_HISTORY else overall)
    return round(left)


def _speed_line(model_left: int, elapsed: float, calls: int) -> str:
    """What the person sees while the model sorts files: how long one takes and how long the files that really go to the model will take at that speed."""
    if calls < 2:
        return "Sorting files"
    each = elapsed / calls
    return (
        f"Sorting files: {each:.0f} s per file, about {_duration(model_left * each)} left"
        if model_left
        else f"Sorting files: {each:.0f} s per file, almost done"
    )


SKIPPED_NO_TEXT = "no readable text"
SKIPPED_BY_RULE = "no amount of money and none of the words your apps declare"  # the gate in `relevance`: such a mail or loose file is not shown to the model
SKIPPED_NOT_A_DOCUMENT = "not a document: no reader for this type of file"  # a program, a database, a video: only the words found inside it are kept


def _why_skipped(d) -> str:
    if not d["text"].strip():
        return SKIPPED_NO_TEXT
    return SKIPPED_NOT_A_DOCUMENT if d["kind"] == "binary" else SKIPPED_BY_RULE


def mark_old_files(conn) -> int:
    """Files sorted before the apps were declared have only the words the model used for what they are. They are marked for the apps whose declared words (apps.json) appear
    in those words: no table of kinds is in the code, and nothing is sent to the model. Done once per file; returns how many were marked."""
    try:
        rows = conn.execute(
            "SELECT id, facts FROM documents WHERE facts<>'' AND json_valid(facts) AND json_extract(facts, '$.apps') IS NULL AND json_extract(facts, '$.kind') IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:  # the database is not made yet
        return 0
    for n, r in enumerate(rows, 1):
        facts = json.loads(r["facts"])
        facts["apps"] = apps.matching(str(facts.get("kind", "")))
        conn.execute("UPDATE documents SET facts=? WHERE id=?", (json.dumps(facts), r["id"]))
        if n % 200 == 0:
            conn.commit()  # in small steps: the database is never held for long, so a read that writes at the same time is not kept waiting
    conn.commit()
    return len(rows)


def _reads_like(conn, d) -> tuple[dict, str] | None:
    """The answer to give a document that reads like one already sorted as about none of the apps, and the name of that one; None when no document reads like it."""
    if d["kind"] == "email" or not d["text"].strip():
        return None
    sig = similar.signature(d["text"])
    found = similar.nearest(conn, sig) if sig else None
    if found is None:
        return None
    row = conn.execute("SELECT name, facts FROM documents WHERE id=?", (found[0],)).fetchone()
    facts = json.loads(row["facts"]) if row and row["facts"] else None
    if not facts or facts.get("apps"):
        return None
    return {"kind": facts.get("kind", ""), "title": facts.get("title", ""), "apps": [], "inherited": True}, row["name"]


def _skippable(d) -> bool:
    """Nothing readable to ask the model about: the file stays, found by its name."""
    if d["kind"] == "binary" or not d["text"].strip():
        return True
    if d["kind"] == "email" and _attachment_count(d) > 0:
        return False  # its attachments are read, and what the mail says about them (who sent it, when it is due) is what makes them mean something
    return d["area"] in ("", "mail", "pictures") and not relevance.worth_reading(d["name"], "email" if d["area"] == "pictures" else d["kind"], d["text"])


def _for_model(d) -> bool:
    return _exact_facts(d) is None and not _skippable(d)


PARALLEL = max(
    1, int(os.environ.get("LIBRARY_PARALLEL", "2"))
)  # model calls in flight at once (the model server works on them together when it is set up to: OLLAMA_NUM_PARALLEL)


class Stopped(Exception):
    """The person pressed Stop while the model was being waited for."""


class StoppableModel:
    """The model client, but a wait for an answer ends the moment Stop is pressed (the answer, if it still comes, is thrown away). Everything else is passed on unchanged."""

    def __init__(self, client, stopping: Callable[[], bool]) -> None:
        self._client, self._stopping = client, stopping

    def __getattr__(self, name: str):
        return getattr(self._client, name)

    def chat(self, *args, **kwargs):
        box: dict[str, Any] = {}

        def call() -> None:
            try:
                box["answer"] = self._client.chat(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - handed back to the thread that waits, whatever it was
                box["error"] = exc

        worker = threading.Thread(target=call, name="model-call", daemon=True)
        worker.start()
        while worker.is_alive():
            worker.join(0.3)
            if self._stopping():
                raise Stopped
        if "error" in box:
            raise box["error"]
        return box["answer"]


class _Ahead:
    """The model identifies up to PARALLEL files at once: while the current file is waited for, the next ones are already being asked. A worker never touches the database or
    the trace (they belong to the reading thread); what it says about its progress is passed on from the reading thread."""

    def __init__(self, client, model: str) -> None:
        self._client, self._model = client, model
        self._pool = ThreadPoolExecutor(max_workers=PARALLEL, thread_name_prefix="identify")
        self._jobs: dict[str, tuple[Future, list[str]]] = {}

    def start(self, d) -> None:
        if d["sha256"] not in self._jobs:
            said: list[str] = []
            self._jobs[d["sha256"]] = (self._pool.submit(_understand, self._client, self._model, d, said.append), said)

    def prefetch(self, chunk: list, after: int, skip: Callable[[Any], bool] | None = None) -> None:
        """Start the model on the next files that need it, so that PARALLEL are in flight (not on those that `skip` says will not need it)."""
        started = 0
        for d in chunk[after + 1 :]:
            if started >= PARALLEL - 1:
                break
            if _for_model(d) and not (skip and skip(d)):
                self.start(d)
                started += 1

    def result(self, d, say: Progress) -> dict:
        """What the model made of this file (waiting for it, and passing on how far a long document has got); raises what the model raised."""
        self.start(d)
        future, said = self._jobs.pop(d["sha256"])
        seen = 0
        while True:
            try:
                return future.result(timeout=0.5)
            except TimeoutError:
                while seen < len(said):
                    say(said[seen])
                    seen += 1

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def judge_pending(
    conn, client, model, progress: Progress | None = None, control: Callable[[], str] | None = None, limit: int = 0, trace: Trace | None = None
) -> dict[str, Any]:
    """Judge every document not yet judged (or `limit` of them: the caller comes back for more, so new files keep being taken in meanwhile). Files from a collection folder you named, and anything else with text worth reading, go to the model; the rest is marked and left alone.
    If the model cannot be reached the document stays as it is and the next round tries again."""
    forget_mail_bodies(conn)
    total = conn.execute("SELECT COUNT(*) FROM documents WHERE judged=0").fetchone()[0]
    out: dict[str, Any] = {"read": 0, "skipped": 0, "waiting": 0, "unclear": 0, "problem": "", "stopped": False}
    began = time.monotonic()
    ahead = _Ahead(client, model)
    try:
        return _judge_chunks(conn, client, model, progress, control, limit, trace, out, total, ahead, began)
    finally:
        ahead.close()


def _judge_chunks(conn, client, model, progress, control, limit, trace, out, total, ahead, began) -> dict[str, Any]:
    index = calls = 0
    for chunk in _pending_chunks(conn):
        for position, d in enumerate(chunk):
            if limit and out["read"] + out["skipped"] >= limit:
                conn.commit()
                return out
            index += 1
            _wait_while_paused(conn, control)
            if control is not None and control() == "stop":
                out["stopped"] = True
                out["waiting"] = total - index + 1
                conn.commit()
                return out
            exact = _exact_facts(d)
            if exact is not None:
                _mark_ready(conn, d["sha256"], 1, exact)
                _trace(trace, d["name"], "sorted", str(exact.get("kind", "")))  # shown by its title, like every other file
            elif (
                kin := _reads_like(conn, d)
            ) is not None:  # it reads almost exactly like a document the model already found to be about none of the apps: the same answer, no model call
                _mark_ready(conn, d["sha256"], 1, kin[0])
                _trace(trace, d["name"], "sorted", f"{kin[0].get('kind', '')}, reads like {kin[1]}")
            elif _skippable(d):  # nothing readable to ask the model about: it stays, found by its name
                why = _why_skipped(d)
                _mark_ready(conn, d["sha256"], 2, {"skipped": why})  # the reason is kept, so what was not shown to the model can be counted and read later
                _trace(trace, d["name"], "skipped", why)
                out["skipped"] += 1
                continue
            else:
                if client is None or not model:
                    out["waiting"] += 1
                    out["problem"] = "The local model is not running, so new files cannot be read yet. Start Ollama and press Read new files again."
                    continue
                if progress:
                    progress(_speed_line(model_work_left(conn), time.monotonic() - began, calls))
                calls += 1
                ahead.prefetch(chunk, position, lambda doc: _reads_like(conn, doc) is not None)
                result, problem = _identify_one(conn, client, model, d, progress, trace, ahead)
                if result == "stopped":
                    out["stopped"] = True
                    out["waiting"] = total - index + 1
                    conn.commit()
                    return out
                if result == "unclear":
                    out["unclear"] += 1
                    continue
                if result == "unreachable":  # the model could not be reached: nothing is marked as done
                    out["waiting"] = total - index + 1
                    out["problem"] = problem
                    conn.commit()
                    return _with_health(conn, client, model, control, out, skip=True)
                if PARALLEL == 1:
                    time.sleep(
                        GENTLE_SECONDS
                    )  # a short rest after each model call, only when one is asked at a time: with two in flight the model is never left idle
            out["read"] += 1
            if index % 20 == 0:
                conn.commit()
        conn.commit()
    return _with_health(conn, client, model, control, out)


def _with_health(conn, client, model, control, out: dict[str, Any], skip: bool = False) -> dict[str, Any]:
    if not skip and client is not None and model and not out["stopped"]:
        out["health_filled"] = fill_health_details(conn, client, model, control)
    return out


def finish_matters(
    conn,
    client,
    model,
    control: Callable[[], str] | None = None,
    progress: Progress | None = None,
    trace: Trace | None = None,
    pairs: int = casebook.MAX_CONFIRMS,
    groups: int = casebook.MAX_READ_PER_PRESS,
    phase: Callable[[int], None] | None = None,
) -> int:
    """Interpretation: the files are grouped (comparing up to `pairs` pairs) and then up to `groups` groups are read. Done in small slices while files are still being identified,
    and in full at the end of a read. Respects Pause and Stop; what is not reached (the model is slow) is counted by `audit` and carried on. Returns how many groups were read."""
    if phase:
        phase(3)
    if progress:
        progress("Finding which files belong together…")
    casebook.rebuild(conn, client, model, control, progress, trace, pairs)
    if phase:
        phase(4)
    done = casebook.understand_pending(conn, client, model, limit=groups, control=control, progress=progress, trace=trace)
    forget_mail_bodies(conn)
    conn.commit()
    return done


def audit(conn) -> dict[str, int]:
    """The check at the end of a read, as plain counts. The first four are what is left (all zero means nothing is left); the last two are the totals."""
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "not_identified": one("SELECT COUNT(*) FROM documents WHERE judged=0 AND TRIM(text)<>''"),
        "no_usable_answer": one("SELECT COUNT(*) FROM documents WHERE judged=3"),
        "not_grouped": one("SELECT COUNT(*) FROM documents WHERE judged=1 AND case_id IS NULL"),
        "matters_not_read": one("SELECT COUNT(*) FROM cases WHERE summary=''"),
        "files": one("SELECT COUNT(*) FROM documents WHERE judged IN (1, 2)"),
        "matters": one("SELECT COUNT(*) FROM cases WHERE summary<>''"),
    }


LEFT = {
    "not_identified": "files the model has not looked at yet",
    "no_usable_answer": "files that could not be sorted (tried again at the next read)",
    "not_grouped": "sorted files not yet placed in a group of related files",
    "matters_not_read": "groups of related files not yet read together",
}


def audit_line(found: dict[str, int]) -> str:
    """What the audit found, with the numbers."""
    left = [f"{found[k]:,} {text}" for k, text in LEFT.items() if found[k]]
    if not left:
        return f"Nothing is left: {found['files']:,} files sorted, in {found['matters']:,} groups of related files, each group read together"
    return "Still left: " + "; ".join(left)


def _apps_clause(names: list[str]) -> tuple[str, list[str]]:
    """A query condition for the files that are about any of these apps: marked for one by the model, or in a folder named after one. No app: nothing."""
    if not names:
        return "0", []
    return "(" + " OR ".join("fact_apps LIKE ? OR area=?" for _ in names) + ")", [v for n in names for v in (f"%|{n}|%", n)]


def fill_health_details(conn, client, model, control: Callable[[], str] | None = None) -> int:
    """Medical documents judged before lab values and medicines were read get them now (one model call each); returns how many."""
    clause, args = _apps_clause(apps.with_reading("medical"))
    rows = conn.execute(
        f"SELECT sha256, name, text, facts FROM documents WHERE judged=1 AND {clause} AND facts<>'' AND json_extract(facts, '$.health') IS NULL",
        args,
    ).fetchall()
    done = 0
    for r in rows:
        if control is not None and control() != "run":
            break
        try:
            details = extract.medical_details(client, model, r["name"], r["text"])
        except extract.Unclear:
            continue  # no usable answer for this one: it keeps what it has and is tried again next time
        except RuntimeError:
            break  # the model could not be reached: the next round tries again
        conn.execute("UPDATE documents SET facts=? WHERE sha256=?", (json.dumps({**json.loads(r["facts"]), "health": details}), r["sha256"]))
        done += 1
    conn.commit()
    return done


# ---- Health: the person's own medical documents, only when unlocked; values and medicines exactly as the documents print them --------------------
def _medical_documents(conn) -> list[dict]:
    clause, args = _apps_clause(apps.with_reading("medical"))
    out = []
    for r in conn.execute(f"SELECT id, name, kind, facts FROM documents WHERE judged=1 AND facts<>'' AND {clause}", args):
        facts = json.loads(r["facts"])
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "file_kind": r["kind"],
                "title": proper_name(facts, r["name"], facts.get("kind", "")),
                "date": facts.get("date") or "",
                "party": facts.get("party") or "",
                "health": facts.get("health") or {},
            }
        )
    return sorted(out, key=lambda d: (d["date"], d["id"]))


def health_funnel(conn) -> dict[str, int]:
    """Why Health may be empty, in counts: how many health documents there are, how many the model has understood, how many hold lab values, and where the rest is stuck."""
    where, args = _apps_clause(apps.with_reading("medical"))

    def count(extra: str = "") -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM documents WHERE {where}{extra}", args).fetchone()[0])

    docs = _medical_documents(conn)
    return {
        "found": count(),
        "understood": len(docs),
        "with_values": sum(1 for d in docs if d["health"].get("values")),
        "waiting_for_the_model": count(" AND judged=0"),
        "not_understood": count(" AND judged=3"),
        "no_readable_text": count(" AND TRIM(text)='' AND kind<>'email'"),
    }


def health_documents(conn) -> dict[str, Any]:
    """Every medical document in date order, newest first: what it is, who it is from, how many values and medicines it holds, and any follow-up it states."""
    docs = [
        {
            "id": d["id"],
            "name": d["name"],
            "title": d["title"],
            "date": d["date"],
            "party": d["party"],
            "values": len(d["health"].get("values") or []),
            "medicines": len(d["health"].get("medicines") or []),
            "follow_up": d["health"].get("follow_up"),
        }
        for d in reversed(_medical_documents(conn))
        if d["file_kind"] != "email"  # the documents, never a whole email
    ]
    return {"documents": docs}


# The common blood and health tests, by the names reports use (English and Dutch). A reading is filed under the common name when its test name matches.
COMMON_TESTS: tuple[tuple[str, str], ...] = (
    ("Hemoglobin", r"\bhemoglobin\w*|\bhaemoglobin\w*|^hb$"),
    ("HbA1c", r"hba1c|hb a1c|geglycosyleerd"),
    ("Glucose", r"\bglucose|\bnuchter"),
    ("Cholesterol (total)", r"cholesterol(?!.*(ldl|hdl))"),
    ("LDL cholesterol", r"\bldl"),
    ("HDL cholesterol", r"\bhdl"),
    ("Triglycerides", r"triglyc\w*"),
    ("Creatinine", r"creatinin\w*|kreatinin\w*"),
    ("eGFR", r"\begfr\b|\bgfr\b"),
    ("TSH", r"\btsh\b"),
    ("Vitamin D", r"vitamin\w* d|25-?oh"),
    ("Vitamin B12", r"vitamin\w* b ?12|\bb12\b"),
    ("Ferritin", r"ferritin\w*"),
    ("CRP", r"\bcrp\b|c-reactiev\w*|c-reactive\w*"),
    ("ALT", r"\balat\b|\balt\b"),
    ("AST", r"\basat\b|\bast\b"),
    ("GGT", r"\bggt\b|gamma-?gt"),
    ("Sodium", r"\bnatrium\b|\bsodium\b"),
    ("Potassium", r"\bkalium\b|\bpotassium\b"),
    ("White blood cells", r"leukocyt\w*|\bwbc\b|white blood"),
    ("Platelets", r"trombocyt\w*|\bplatelet\w*"),
    ("Hematocrit", r"hematocriet|haematocrit|hematocrit"),
)
_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_BETWEEN = re.compile(rf"^\s*({_NUM})\s*(?:-|–|—|tot|to)\s*({_NUM})\s*[a-zA-Zµ%/ ]*$")
_BELOW = re.compile(rf"^\s*(<|≤|<=)\s*({_NUM})")
_ABOVE = re.compile(rf"^\s*(>|≥|>=)\s*({_NUM})")


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def range_flag(number: float | None, printed: str) -> str:
    """Whether a result lies inside the reference range the report itself prints: in_range, below_range, above_range, or no_range when there is no number or no
    range that can be read. Only a comparison with the printed range: not a judgement about health."""
    if number is None or not printed:
        return "no_range"
    if m := _BETWEEN.match(printed):
        low, high = sorted((_to_float(m.group(1)), _to_float(m.group(2))))
        return "below_range" if number < low else "above_range" if number > high else "in_range"
    if m := _BELOW.match(printed):
        limit = _to_float(m.group(2))
        return "in_range" if (number < limit if m.group(1) == "<" else number <= limit) else "above_range"
    if m := _ABOVE.match(printed):
        limit = _to_float(m.group(2))
        return "in_range" if (number > limit if m.group(1) == ">" else number >= limit) else "below_range"
    return "no_range"


def _common_name(test: str) -> str:
    lower = " ".join(test.lower().split())
    for name, pattern in COMMON_TESTS:
        if re.search(pattern, lower):
            return name
    return ""


def health_values(conn, test: str = "") -> dict[str, Any]:
    """Each measurement over time exactly as the documents print it, grouped (the common tests under their common names), with for each: the latest result, whether
    it lies inside the reference range printed on that report, and how it changed since the reading before. Never interpreted."""
    groups: dict[str, dict[str, Any]] = {}
    for d in _medical_documents(conn):
        for v in d["health"].get("values") or []:
            common = _common_name(v["test"])
            name = common or " ".join(v["test"].split())
            if test and test.lower() not in name.lower() and test.lower() not in v["test"].lower():
                continue
            group = groups.setdefault(name.lower(), {"test": name, "common": bool(common), "unit": "", "readings": []})
            group["unit"] = group["unit"] or v.get("unit") or ""
            group["readings"].append(
                {
                    "date": d["date"],
                    "value": v["value"],
                    "number": v.get("number"),
                    "unit": v.get("unit") or "",
                    "range": v.get("range") or "",
                    "flag": range_flag(v.get("number"), v.get("range") or ""),
                    "document": d["name"],
                    "id": d["id"],
                }
            )
    for g in groups.values():
        g["readings"].sort(key=lambda r: (r["date"], r["id"]))
        latest = g["readings"][-1]
        g["latest"], g["flag"] = latest, latest["flag"]
        g["change"] = None
        before = next((r for r in reversed(g["readings"][:-1]) if r["number"] is not None), None)
        if before is not None and latest["number"] is not None:
            diff = round(latest["number"] - before["number"], 4)
            g["change"] = {
                "since": before["date"],
                "absolute": round(diff, 2),
                "percent": round(diff / before["number"] * 100, 1) if before["number"] else None,
                "direction": "up" if diff > 0 else "down" if diff < 0 else "same",
            }
    ordered = sorted(groups.values(), key=lambda g: g["test"].lower())
    order = {name: i for i, (name, _p) in enumerate(COMMON_TESTS)}
    common_list = sorted((g for g in ordered if g["common"]), key=lambda g: order[g["test"]])
    return {
        "tests": ordered,
        "attention": [g for g in ordered if g["flag"] in ("above_range", "below_range")],
        "common": common_list,
        "other": [g for g in ordered if not g["common"]],
        "note": "A flag only compares a result with the reference range printed on that report. It is not a diagnosis or advice.",
    }


def health_medicines(conn) -> dict[str, Any]:
    """Every medicine a document prescribes, newest first, with the dose and duration as printed."""
    meds = [
        {"name": m["name"], "dose": m.get("dose") or "", "duration": m.get("duration") or "", "date": d["date"], "document": d["name"], "id": d["id"]}
        for d in reversed(_medical_documents(conn))
        for m in d["health"].get("medicines") or []
    ]
    return {"medicines": meds}


def health_followups(conn, today: str) -> dict[str, Any]:
    """Follow-up or next-appointment dates the documents state, from today on."""
    ups = sorted(
        (
            {"date": d["health"]["follow_up"], "document": d["name"], "title": d["title"], "id": d["id"]}
            for d in _medical_documents(conn)
            if d["health"].get("follow_up", "") and d["health"]["follow_up"] >= today
        ),
        key=lambda x: x["date"],
    )
    return {"follow_ups": ups}


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
        elif r["judged"] == 3:
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


def list_documents(
    conn,
    kinds: list[str] | None = None,
    area: str = "",
    place: str = "",
    year: str = "",
    since: int = 0,
    limit: int = 100,
    full: bool = False,
    source: str = "",
    only_understood: bool = False,
    app: str = "",
) -> list[dict]:
    """Ready documents, oldest first. `app` is an app the model marked the file for; `kinds` are words looked for in what the model called the file; with `area`, a document also
    qualifies when it came from that area. Without any of them, everything the model found to be about some app is returned. With `full`, the text and structured data come too."""
    wanted = {k.lower() for k in kinds or [] if k}
    out: list[dict] = []
    where = "ready > ?"
    args: list[Any] = [max(0, int(since))]
    if app and not area:
        where += " AND fact_apps LIKE ?"
        args.append(f"%|{app}|%")
    elif wanted and not area:
        where += " AND (" + " OR ".join("LOWER(COALESCE(fact_kind, '')) LIKE ?" for _ in wanted) + ")"
        args += [f"%{w}%" for w in sorted(wanted)]
    for r in conn.execute(f"SELECT {LIST_COLUMNS} FROM documents WHERE {where} ORDER BY ready", args):
        doc = _as_document(r)
        if not _fits(doc, wanted, area, source, only_understood, app):
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


def trip_documents(conn, limit: int = 500) -> list[dict]:
    """The files that are about a trip: those marked for an app that reads trips (`apps.json`)."""
    found: list[dict] = []
    for name in apps.with_reading("trip"):
        found += list_documents(conn, app=name, limit=limit)
    return found


def is_trip_document(doc: dict) -> bool:
    return bool(set(doc["apps"]) & set(apps.with_reading("trip")))


# ---- trips: derived from the tickets and bookings that were read -----------------------------------------------------------------
def trips(conn, place: str = "", year: str = "") -> list[dict]:
    """Journeys found in the tickets and bookings: where, from which day to which day (as the documents themselves write them), and how many
    documents show it. Documents for the same place whose dates are within 60 days of each other are one trip. Most documents first."""
    found: dict[str, list[dict]] = {}
    for doc in trip_documents(conn):
        facts = doc["facts"]
        start, name = str(facts.get("start_date") or ""), str(facts.get("place") or "").strip()
        if not start or not name:
            continue
        if place and place.lower() not in name.lower():
            continue
        found.setdefault(name.casefold(), []).append({"place": name, "start": start, "end": str(facts.get("end_date") or start)})
    out: list[dict] = []
    for group in found.values():
        group.sort(key=lambda d: d["start"])
        current: list[dict] = []
        for d in group:
            if current and (date.fromisoformat(d["start"]) - date.fromisoformat(max(c["end"] for c in current))).days > TRIP_GAP_DAYS:
                out.append(_trip(current))
                current = []
            current.append(d)
        out.append(_trip(current))
    if year:
        out = [t for t in out if t["start"].startswith(year) or t["end"].startswith(year)]
    return sorted(out, key=lambda t: (-t["documents"], t["start"]))


TRIP_GAP_DAYS = 60


def _trip(docs: list[dict]) -> dict:
    return {"place": docs[0]["place"], "start": min(d["start"] for d in docs), "end": max(d["end"] for d in docs), "documents": len(docs)}


def documents_between(conn, start: str, end: str, limit: int = 100) -> list[dict]:
    """Every recognised document dated within the window (its own date, or the dates of a ticket or booking), oldest first."""
    out: list[dict] = []
    for doc in list_documents(conn, limit=500, source="documents"):  # documents, never a whole email
        facts = doc["facts"]
        day = str(facts.get("start_date") or facts.get("date") or "")
        if day and start <= day <= end:
            out.append(doc)
        if len(out) >= limit:
            break
    return sorted(out, key=lambda d: str(d["facts"].get("start_date") or d["facts"].get("date")))


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
            (sha, str(r["name"])[:255], "image", str(r["text"])[:MAX_TEXT], "pictures", "", ""),
        )
        added += cur.rowcount
    conn.commit()
    return added
