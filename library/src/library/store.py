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
import threading
import time
from collections.abc import Callable, Iterator
from datetime import date
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


def ingest_dir(conn, directory: Path, stop=None) -> dict[str, int]:
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
            "INSERT OR IGNORE INTO documents (sha256, name, kind, text, area, data, parsed_at, source) VALUES (?,?,?,?,?,?,?,?)",
            (d["sha256"], d["name"], d["kind"], d["text"], area, _structured(d), str(d.get("parsed_at", ""))[:25], source),
        )
        if cur.rowcount and source:
            replaced += _replace_older_versions(conn, directory, source, d["sha256"])
        new += cur.rowcount
        known += 1 - cur.rowcount
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
    # A whole email is never kept: once it is judged only what it says (title, who, when, reference) stays. Its attachments are documents of their own.
    conn.execute("UPDATE documents SET text=?, data='' WHERE sha256=? AND area='mail' AND kind='email'", (_mail_summary(facts), sha))


def forget_mail_bodies(conn) -> int:
    """Emails judged before this rule keep only what they say too; returns how many were cut down."""
    done = 0
    while True:
        rows = conn.execute(
            "SELECT id, facts FROM documents WHERE area='mail' AND kind='email' AND judged>0 AND length(text)>? LIMIT 500", (MAIL_KEPT_CHARS,)
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


def _exact_facts(d) -> dict | None:
    """Documents that need no model: a bank standard (MT940, camt.053), the ECB's exchange-rate file, or a picture with no text in it (a photo)."""
    if recognise.bank_standard(d["text"]):
        return {"kind": "bank_statement", "title": "Bank statement"}
    if recognise.exchange_rate_file(_data(d).get("rows")):
        return {"kind": "other", "title": "ECB exchange rates"}
    if d["kind"] == "image" and len(d["text"].strip()) < relevance.MIN_TEXT:  # a picture with no text in it is a photo, not a document: Photos' business
        return {"kind": "photo", "title": d["name"]}
    return None


JUDGE_CHUNK = 100  # documents held in memory at a time: tens of thousands of mails never sit in memory together


def _wait_while_paused(conn, control: Callable[[], str] | None) -> None:
    while control is not None and control() == "pause":  # paused by the person: wait here, nothing is lost
        conn.commit()
        time.sleep(0.5)


def _understand(client, model: str, d) -> dict:
    """What the model makes of one document: what it is and its key facts, and for a medical document the lab values and medicines the document itself prints."""
    facts = extract.classify(client, model, d["name"], d["text"])
    if facts.get("kind") in HEALTH_KINDS or d["area"] == "health":
        facts["health"] = extract.medical_details(client, model, d["name"], d["text"])
    return facts


def judge_pending(conn, client, model, progress: Progress | None = None, control: Callable[[], str] | None = None, limit: int = 0) -> dict[str, Any]:
    """Judge every document not yet judged (or `limit` of them: the caller comes back for more, so new files keep being taken in meanwhile). Files from a collection folder you named, and anything else with text worth reading, go to the model; the rest is marked and left alone.
    If the model cannot be reached the document stays as it is and the next round tries again."""
    forget_mail_bodies(conn)
    total = conn.execute("SELECT COUNT(*) FROM documents WHERE judged=0").fetchone()[0]
    out: dict[str, Any] = {"read": 0, "skipped": 0, "waiting": 0, "unclear": 0, "problem": "", "stopped": False}
    index, last = 0, 0
    while True:
        chunk = conn.execute(
            "SELECT id, sha256, name, kind, text, data, area FROM documents WHERE judged=0 AND id>? ORDER BY id LIMIT ?", (last, JUDGE_CHUNK)
        ).fetchall()
        if not chunk:
            break
        for d in chunk:
            if limit and out["read"] + out["skipped"] >= limit:
                conn.commit()
                return out
            index += 1
            last = d["id"]
            _wait_while_paused(conn, control)
            if control is not None and control() == "stop":
                out["stopped"] = True
                out["waiting"] = total - index + 1
                conn.commit()
                return out
            exact = _exact_facts(d)
            if exact is not None:
                _mark_ready(conn, d["sha256"], 1, exact)
            elif (
                d["kind"] == "binary"
                or not d["text"].strip()
                or (
                    d["area"] in ("", "mail", "pictures")
                    and not relevance.worth_reading(d["name"], "email" if d["area"] == "pictures" else d["kind"], d["text"])
                )
            ):  # nothing readable to ask the model about: it stays, found by its name
                _mark_ready(conn, d["sha256"], 2, None)
                out["skipped"] += 1
                continue
            else:
                if client is None or not model:
                    out["waiting"] += 1
                    out["problem"] = "The local model is not running, so new files cannot be read yet. Start Ollama and press Read new files again."
                    continue
                if progress and index % 5 == 1:
                    progress(f"{index} read so far")  # the total is not known: more files may still be arriving
                try:
                    facts = _understand(client, model, d)
                except extract.Unclear:  # the model answered but could not make sense of it: not 'other', not lost: counted and tried again at the next Read
                    conn.execute("UPDATE documents SET judged=3 WHERE sha256=?", (d["sha256"],))
                    out["unclear"] += 1
                    continue
                except RuntimeError as exc:  # the model could not be reached: nothing is marked as done
                    out["waiting"] = total - index + 1
                    out["problem"] = str(exc)
                    conn.commit()
                    return _with_health(conn, client, model, control, out, skip=True)
                _mark_ready(conn, d["sha256"], 1, facts)
                time.sleep(GENTLE_SECONDS)  # a short rest after each model call: the computer stays responsive while many documents are read
            out["read"] += 1
            if index % 20 == 0:
                conn.commit()
        conn.commit()
    return _with_health(conn, client, model, control, out)


def _with_health(conn, client, model, control, out: dict[str, Any], skip: bool = False) -> dict[str, Any]:
    if not skip and client is not None and model and not out["stopped"]:
        out["health_filled"] = fill_health_details(conn, client, model, control)
    return out


def fill_health_details(conn, client, model, control: Callable[[], str] | None = None) -> int:
    """Medical documents judged before lab values and medicines were read get them now (one model call each); returns how many."""
    marks = ",".join("?" for _ in HEALTH_KINDS)
    rows = conn.execute(
        f"SELECT sha256, name, text, facts FROM documents WHERE judged=1 AND (fact_kind IN ({marks}) OR area='health') AND facts<>'' AND facts NOT LIKE '%\"health\"%'",
        sorted(HEALTH_KINDS),
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
    marks = ",".join("?" for _ in HEALTH_KINDS)
    out = []
    for r in conn.execute(
        f"SELECT id, name, kind, facts FROM documents WHERE judged=1 AND facts<>'' AND (fact_kind IN ({marks}) OR area='health')", sorted(HEALTH_KINDS)
    ):
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
GENTLE_SECONDS = float(os.environ.get("LIBRARY_GENTLE_SECONDS", "0.5"))
LIST_COLUMNS = "id, sha256, name, kind, area, parsed_at, facts, ready"


# ---- Health: medical documents are recognised by kind or by the health folder
HEALTH_KINDS = frozenset({"medical"})


def _is_health(facts_json: str, area: str = "") -> bool:
    """A medical document: the model said so, or it lies in the person's health folder (whatever the model said)."""
    return area == "health" or (bool(facts_json) and json.loads(facts_json).get("kind") in HEALTH_KINDS)


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
        "kind": facts.get("kind", "other"),
        "facts": facts,
        "ready": r["ready"],
    }
    return doc


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
) -> list[dict]:
    """Ready documents, oldest first. `kinds` are classified kinds (invoice, ticket, medical ...); a document is returned when its kind is listed or, with `area`, when it came from that area.
    Without either, everything the model recognised (not "other") is returned. With `full`, the text and structured data come too."""
    wanted = set(kinds or [])
    out: list[dict] = []
    where = "ready > ?"
    args: list[Any] = [max(0, int(since))]
    if wanted and not area:
        where += f" AND fact_kind IN ({','.join('?' for _ in wanted)})"
        args += sorted(wanted)
    for r in conn.execute(f"SELECT {LIST_COLUMNS} FROM documents WHERE {where} ORDER BY ready", args):
        doc = _as_document(r)
        if (doc["kind"] in HEALTH_KINDS or doc["area"] == "health") and "medical" not in wanted and area != "health":
            continue  # medical documents go to whoever asks for them by name, never to another app that asks for its own kinds or for everything
        if source == "documents":  # documents from folders and the documents inside emails, never a whole email
            if doc["file_kind"] == "email":
                continue
        elif source and (doc["area"] == "mail") != (source == "mail"):  # `mail` only the mail; `files` everything else
            continue
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


def retry_unclear(conn) -> int:
    """Documents the model could not make sense of get another try (called when the person presses Read new files)."""
    n = conn.execute("UPDATE documents SET judged=0 WHERE judged=3").rowcount
    conn.commit()
    return n


def by_kind(conn) -> list[dict]:
    """How many documents of each recognised kind there are."""
    out = [
        {"kind": r[0] or "other", "count": r[1]}
        for r in conn.execute("SELECT fact_kind, COUNT(*) FROM documents WHERE judged=1 AND fact_kind IS NOT NULL GROUP BY fact_kind ORDER BY COUNT(*) DESC")
    ]
    return out


# ---- trips: derived from the tickets and bookings that were read -----------------------------------------------------------------
def trips(conn, place: str = "", year: str = "") -> list[dict]:
    """Journeys found in the tickets and bookings: where, from which day to which day (as the documents themselves write them), and how many
    documents show it. Documents for the same place whose dates are within 60 days of each other are one trip. Most documents first."""
    found: dict[str, list[dict]] = {}
    for doc in list_documents(conn, ["ticket", "booking"], limit=500):
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


# ---- pictures of documents: a photographed receipt or letter is read like any other document ---------------------------------------------
PICTURE_ROOTS = ("Inbox/", "MailPictures/")  # these are read by the document reader already: only photos from the photo folder itself are added here


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
