"""Where an Update stands, in the words the person knows: the steps, the counts, the time left."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from kit import log

from . import appstate, judging, pictures, readreport, seal, store, trace
from .appstate import State

PERCENT_ONE_DECIMAL_BELOW = 10  # below this a percentage is shown with one decimal


def _get_status(state: State, conn, query: dict[str, str]) -> dict:
    return _cached("status", lambda c: {**store.counts(c), "kinds": store.by_kind(c)}, state, conn)


def _found() -> dict[str, Any]:
    """What the reader has counted so far in its folders: each total is there as soon as it is known (the documents first, then the mails and what they carry)."""
    try:
        data = json.loads(seal.read_note(appstate.parsed_dir() / ".found"))
        found: dict[str, Any] = {
            "mail_connected": data.get("mail_connected") is True,
            "by_folder": {str(k)[:20]: int(v) for k, v in (data.get("by_folder") or {}).items()},
        }
        for key in ("documents", "mails", "attachments"):
            if key in data:
                found[key] = int(data[key])
        return found
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _progress() -> dict[str, Any]:
    try:
        return json.loads(seal.read_note(appstate.parsed_dir() / ".progress"))
    except (OSError, ValueError):
        return {}


def _gone_through() -> dict[str, int]:
    """How many of the counted files, mails and attachments the reader has read fully and successfully in this round (a file read before, or identical to one read, counts: it is read)."""
    data = _progress()
    try:
        return {k: int(data[k]) for k in ("documents", "mails", "attachments")}
    except (KeyError, TypeError, ValueError):
        return {}


def _unread_files() -> list[str]:
    """The files (and mails) the reader could not read in its last round, each with the reason: the reader writes them down, the card names them."""
    try:
        raw = json.loads(seal.read_note(appstate.parsed_dir() / ".unread-files"))
    except (OSError, ValueError):
        return []
    return [str(item)[:220] for item in raw[:50]] if isinstance(raw, list) else []


def _unread() -> dict[str, int]:
    """How many it could not read: failed, or too large. They are said, never counted as read."""
    raw = _progress().get("unread")
    try:
        return {k: int(raw[k]) for k in ("documents", "mails", "attachments")} if isinstance(raw, dict) else {}
    except (KeyError, TypeError, ValueError):
        return {}


def _row(name: str, read: int, total: int | None, noun: str) -> dict[str, Any]:
    """One line of the Update, in files (or mails), the way the person counts them: "12 of 36 files" while reading, "36 files" when done."""
    if total is not None and read < total:
        return {"name": name, "detail": f"{read:,} of {total:,} {noun}"}
    return {"name": name, "detail": f"{max(read, total or 0):,} {noun}"}


# One file can become many documents (an archive, a mail with attachments), so files are counted by the name of the file they came from.
_FILE_OF = "area || '|' || substr(name, 1, instr(name || '/', '/') - 1)"


_CACHE: dict[str, tuple[float, Any]] = {}
FIRST_GUESS_SECONDS = 15.0  # how long a file is guessed to take (marked with ~) until one has finished in this read
STATUS_TTL = 3.0  # the page asks every second or so while an Update runs; counting a big library more often than this is wasted work


_REFRESHING: set[str] = set()
_REFRESH_LOCK = threading.Lock()


def _cached(key: str, make, state: State | None = None, conn=None, first=None):
    """The answer of `make(conn)`, reused for a few seconds. When the answer is older than that it is still given at once, and brought up to date in the background
    (on its own connection): a status question never waits for the database, however busy a big read keeps it. Only the very first time is it worked out on the spot."""
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < STATUS_TTL:
        return hit[1]
    if hit and state is not None:
        with _REFRESH_LOCK:
            if key not in _REFRESHING:
                _REFRESHING.add(key)
                threading.Thread(target=_refresh, args=(key, make, state), name=f"refresh-{key}", daemon=True).start()
        return hit[1]
    if first is not None and state is not None:  # nothing known yet: say what can be said at once, and work the numbers out in the background
        with _REFRESH_LOCK:
            if key not in _REFRESHING:
                _REFRESHING.add(key)
                threading.Thread(target=_refresh, args=(key, make, state), name=f"refresh-{key}", daemon=True).start()
        return first
    value = make(conn)
    _CACHE[key] = (now, value)
    return value


def _refresh(key: str, make, state: State) -> None:
    conn = state.connect()
    try:
        _CACHE[key] = (time.monotonic(), make(conn))
    except Exception as exc:  # noqa: BLE001 - the old answer stays; it is tried again at the next question
        log.failed("status refresh failed", exc, key=key)
    finally:
        conn.close()
        with _REFRESH_LOCK:
            _REFRESHING.discard(key)


def _parts(state: State, conn) -> list[dict[str, Any]]:
    """What the Update shows: Documents, Photos and Mails, each as a number of files the person can check."""
    return _cached("parts", lambda c: _parts_now(state, c), state, conn)


def _percent(part: int, whole: int) -> str:
    """Whole numbers from 10% up, one decimal below (so 17 of 1,201 reads 1.4%, never a misleading 0% or 1%); 100% only when it really is."""
    if not whole:
        return "0%"
    value = part * 100 / whole
    return "100%" if part == whole else f"{value:.1f}%" if value < PERCENT_ONE_DECIMAL_BELOW else f"{min(value, 99):.0f}%"


def _states(conn, where: str) -> dict[str, int]:
    """Files by what has happened to them: identified by the model, skipped (nothing to read in them), waiting for the model, or no usable answer yet."""

    def count(judged: str) -> int:
        return conn.execute(f"SELECT COUNT(DISTINCT {_FILE_OF}) FROM documents WHERE {where} AND judged{judged}").fetchone()[0]

    return {"identified": count("=1"), "aside": count("=2"), "waiting": count("=0"), "unclear": count("=3")}


def _need_share(states: dict[str, int]) -> float:
    """How far the files that need the model have got (sorted of sorted, to do and could not be sorted); skipped files are not part of it."""
    return _share(states["identified"], states["identified"] + states["waiting"] + states["unclear"])


def _share(part: int, whole: int) -> float:
    """How much of the whole is done, 0 to 100; 100 only when it really is all of it."""
    return 0.0 if not whole else 100.0 if part >= whole else round(min(part * 100 / whole, 99.9), 1)


def _understood(conn, where: str) -> str:
    """What has happened to the files so far, in plain counts: identified by the model, skipped (nothing to read), waiting, no usable answer."""
    s = _states(conn, where)
    if not any(s.values()):
        return ""
    line = f" · {s['identified']:,} sorted"
    for key, label in (("waiting", "to do"), ("unclear", "could not be sorted"), ("aside", "skipped")):
        line += f" · {s[key]:,} {label}" if s[key] else ""
    return line


def _parts_now(state: State, conn) -> list[dict[str, Any]]:
    found = _found()
    files = conn.execute(f"SELECT COUNT(DISTINCT {_FILE_OF}) FROM documents WHERE area NOT IN ('mail','pictures')").fetchone()[0]
    mails = conn.execute(f"SELECT COUNT(DISTINCT {_FILE_OF}) FROM documents WHERE area='mail'").fetchone()[0]
    mail_row = _row("Mails", mails, found.get("mails"), "mails")
    if found and not found.get("mail_connected") and not mails and not found.get("mails"):
        mail_row = {"name": "Mails", "detail": "not connected: Apple Mail was not given to Atlas (see the README, Mail)"}
    docs_row = _row("Documents", files, found.get("documents"), "files")
    docs_row["detail"] += _understood(conn, "area NOT IN ('mail','pictures')")
    docs_row["percent"] = _need_share(_states(conn, "area NOT IN ('mail','pictures')"))
    if mail_row.get("detail", "").find("not connected") < 0:
        mail_row["detail"] += _understood(conn, "area='mail'")
        mail_row["percent"] = _need_share(_states(conn, "area='mail'"))
    shares = [
        f"{'Other' if k == 'inbox' else k.capitalize()} {v:,}" for k, v in found.get("by_folder", {}).items() if v
    ]  # where the number comes from; empty folders are left out
    if len(shares) > 1:
        docs_row["detail"] += " · " + " · ".join(shares)
    not_read = sum(readreport.unread_counts().values())
    if not_read:
        docs_row["detail"] += f" · {not_read:,} not read (ask Atlas why)"
    rows = [docs_row, mail_row]
    engine = state.engine()
    if engine is None:
        rows.insert(1, {"name": "Photos", "detail": "not connected: the photo drive was not found when Documents started"})
    else:
        c = pictures.counts(engine)
        rows.insert(1, {**_row("Photos", c["indexed"], c["pictures"], "photos"), "percent": _share(c["indexed"], c["pictures"])})
    return rows


def _control(state: State, action: str) -> dict:
    """Pause, resume or stop the Update that is running: the reader and the model both wait or end at their next safe point; nothing already read is lost."""
    if not state.scan["running"]:
        return {"ok": False, "error": "nothing is being read right now"}
    appstate.parsed_dir().mkdir(parents=True, exist_ok=True)
    pause, stop = appstate.parsed_dir() / ".pause", appstate.parsed_dir() / ".stop"
    if action == "pause":
        pause.touch()
    elif action == "resume":
        pause.unlink(missing_ok=True)
    else:
        stop.touch()
        pause.unlink(missing_ok=True)
    state.control = {"pause": "pause", "resume": "run", "stop": "stop"}[action]
    return {"ok": True, "control": state.control}


def backlog(conn) -> int:
    """Files known to be waiting: documents read but not understood yet, plus what the last count found beyond what is already stored (0 when there has been no count)."""
    found = _found()
    stored = conn.execute(f"SELECT COUNT(DISTINCT {_FILE_OF}) FROM documents WHERE area NOT IN ('mail','pictures')").fetchone()[0]
    stored_mail = conn.execute(f"SELECT COUNT(DISTINCT {_FILE_OF}) FROM documents WHERE area='mail'").fetchone()[0]
    unread = max(0, found.get("documents", 0) - stored) + max(0, found.get("mails", 0) - stored_mail)
    return unread + store.counts(conn)["waiting"]


def _step_state(running: bool, done: bool) -> str:
    return "running" if running else "done" if done else "waiting"


SORT_ORDER = (
    "documents",
    "mails",
    "attachments",
)  # sorting and grouping: the files in your folders first, then the mail and what it carries (the reader takes the mail first)
STEP_WORDS = (
    ("Read", "Reading files", "Get the text out of every file"),
    ("Sort", "Sorting files", "Find out what each file is"),
    ("Group", "Grouping related files", "Put files about the same thing together and read them as one"),
)


def _steps_for_now(s: dict[str, Any]) -> list[dict[str, Any]]:
    """The three steps with no numbers yet: shown at once while the counts are being worked out, so the card is never empty."""
    phase = s.get("phase")
    running = [
        phase == appstate.PHASE_READ or (appstate.parsed_dir() / ".busy").exists(),
        phase == appstate.PHASE_SORT,
        phase in (appstate.PHASE_GROUP, appstate.PHASE_FINISH),
    ]
    return [
        {"n": n, "name": name, "doing": doing, "about": text, "state": "running" if running[n - 1] else "waiting", "counts": [], "detail": "", "percent": 0.0}
        for n, (name, doing, text) in enumerate(STEP_WORDS, 1)
    ]


def _copies(n: int, taken_in: bool, total: int, held: int, unread: int) -> int:
    """Counted files that are the same as another one (a logo in a hundred mails is one document): once the reading is over every counted file is held, copied or unreadable."""
    return max(0, total - held - unread) if n == 1 and taken_in else 0


def _done_count(c: _Context, n: int, key: str, where: str, total: int) -> int:
    held, taken_in, gone_through = c.tally[key], c.taken_in, c.gone_through
    if (c.s.get("phase") or 1) < n:
        return 0  # a step that has not begun has done nothing, whatever state the files are already in
    if n == 1:
        return (
            min(total, max(held["present"], gone_through.get(key, 0))) if not taken_in else min(total, held["present"])
        )  # what is held: each different document once
    return held[where]


def _tally(conn) -> dict[str, dict[str, int]]:
    """How far the files have got, in one pass over the database: for the documents (files in the folders, counted by the file they came from), the mails and the documents in mails,
    how many are in, sorted and understood, and how many attachments the mails say they carried."""
    out = {g: {"present": 0, "sorted": 0, "understood": 0, "promised": 0} for g in ("documents", "mails", "attachments")}
    rows = conn.execute(
        f"""SELECT g, COUNT(DISTINCT f) AS present,
                   COUNT(DISTINCT CASE WHEN judged IN (1, 2) THEN f END) AS sorted,
                   COUNT(DISTINCT CASE WHEN judged=2 OR (judged=1 AND case_id IS NOT NULL) THEN f END) AS understood,
                   COALESCE(SUM(promised), 0) AS promised
            FROM (SELECT CASE WHEN area='mail' AND kind='email' THEN 'mails' WHEN area='mail' THEN 'attachments' ELSE 'documents' END AS g,
                         CASE WHEN area='mail' THEN CAST(id AS TEXT) ELSE {_FILE_OF} END AS f, judged, case_id, promised
                  FROM documents WHERE area<>'pictures')
            GROUP BY g"""
    )
    for r in rows:
        out[r["g"]] = {k: int(r[k]) for k in ("present", "sorted", "understood", "promised")}
    out["attachments"]["promised"] = out["mails"]["promised"]  # carried by the mails
    return out


@dataclass
class _Context:
    """What every count of every step is worked out from, gathered once per request."""

    s: dict[str, Any]
    found: dict[str, Any]
    tally: dict[str, dict[str, int]]
    promised: int  # every mail says how many attachments it carried: that is how many documents in mails there are to read, taken out yet or not
    known: dict[str, Any]  # what the reader counted before it started, per group
    gone_through: dict[str, int]
    unread: dict[str, int]
    taken_in: bool  # step 1 is over


LABELS = {
    "mails": "mails",
    "attachments": "documents in mails",
    "documents": "documents",
}  # in the order they are read: the mails, what they carry, then the documents


def _context(conn, s: dict[str, Any]) -> _Context:
    found = _found()
    tally = _tally(conn)
    promised = tally["attachments"]["promised"]
    known = {key: found.get(key) for key in LABELS}  # the reader counts all three before it starts
    gone_through = _gone_through()
    unread = _unread()
    for group, n in (s.get("rejected") or {}).items():
        unread[group] = unread.get(group, 0) + n  # results the service would not take in are not read either
    mails_read = bool(found) and gone_through.get("mails", 0) + unread.get("mails", 0) >= int(found.get("mails") or 0)
    gone_through = {
        **gone_through,
        "attachments": gone_through.get("attachments", 0) + (promised if mails_read else 0),
    }  # the ones inside the messages are read with their mail
    return _Context(s, found, tally, promised, known, gone_through, unread, (s.get("phase") or 0) >= appstate.PHASE_SORT)


def _count_line(c: _Context, n: int, key: str, label: str, where: str) -> dict[str, Any]:
    """One count of one step. Step 1 counts the files the reader counted, each once it has been gone through (read, already known, or left out); sorting and grouping count what is held."""
    held = c.tally[key]["present"]
    total = held  # sorting and grouping count what is held
    if n == 1:
        counted = (c.known[key] or 0) + (
            c.promised if key == "attachments" else 0
        )  # for the documents in mails: those Mail keeps as files of their own, plus the ones inside the messages
        total = max(held, counted)
    copies = _copies(n, c.taken_in, total, held, c.unread.get(key, 0))
    if n == 1 and c.taken_in:
        total = held  # once the reading is over there is one number for the documents: the different ones held, the same in every step (copies and unreadable files are said beside it)
    return {
        "key": key,
        "label": label,
        "done": _done_count(c, n, key, where, total),
        "unread": c.unread.get(key, 0) if n == 1 else 0,
        "copies": copies,
        "total": total,
        "known": c.taken_in or key in c.found,  # each gives its number as soon as its total is known; until then it says it is counting
    }


def _step(c: _Context, n: int, words: tuple[str, str, str], where: str, running: bool) -> dict[str, Any]:
    name, doing, text = words
    items = (
        LABELS.items() if n == 1 else sorted(LABELS.items(), key=lambda kv: SORT_ORDER.index(kv[0]))
    )  # each step lists them in the order it works through them
    every = [_count_line(c, n, key, label, where) for key, label in items]
    begun = n == 1 or (c.s.get("phase") or 1) >= n  # a step that has not begun shows no numbers: they would only disagree with the step still running
    counts = every if begun else []
    shown = [x for x in counts if x["known"]]
    done, total = sum(int(x["done"]) for x in shown), sum(int(x["total"]) for x in shown)
    everything = (n == 1 and c.taken_in) or (bool(sum(int(x["total"]) for x in every)) and all(int(x["done"]) >= int(x["total"]) for x in every if x["total"]))
    return {
        "n": n,
        "name": name,
        "doing": doing,
        "about": text,
        "state": _step_state(running, everything),
        "counts": counts,
        "detail": "",
        "percent": _share(done, total),
    }


def _steps(conn, s: dict[str, Any]) -> list[dict[str, Any]]:
    """The three steps of a read. 1 Read: the text of every file is taken out. 2 Sort: every file is sorted or, when the model has no use for it, dealt with. 3 Group: related
    files are connected and read together. Each step counts three things apart, the way the person knows them: the documents (files in the folders), the mails, and the documents
    inside mails. A step is done when all of them are."""
    c = _context(conn, s)
    stages = (
        ("present", (appstate.parsed_dir() / ".busy").exists() or s.get("phase") == 1),
        ("sorted", s.get("phase") == appstate.PHASE_SORT),
        ("understood", s.get("phase") in (3, 4)),
    )
    return [_step(c, n, words, where, running) for n, (words, (where, running)) in enumerate(zip(STEP_WORDS, stages, strict=True), 1)]


def _reading_now(s: dict[str, Any]) -> dict[str, Any] | None:
    """Step 1: the file the reader says it is on (it writes the name as it starts each one), and how long it has been on it."""
    try:
        name, _, step = seal.read_note(appstate.parsed_dir() / ".now")[:400].partition("\n")
    except (OSError, ValueError):  # no note yet, or a sealed one this app cannot open
        return None
    if not name:
        return None
    step = step.strip() or "reading the text"
    if s.get("reading_name") != name:
        s["reading_name"], s["reading_since"] = name, time.monotonic()
    return {"name": name, "step": step, "percent": None, "estimated": False, "seconds": int(time.monotonic() - s["reading_since"])}


def _file_now(s: dict[str, Any], conn) -> dict[str, Any] | None:
    """The file being worked on: what is being done to it, the seconds so far and how far along it is. A medical document read in parts is exact for the parts finished
    (part 3 of 9 means two are done) and, inside the part being read, an estimate from how long a model call usually takes (`estimated`), so the bar keeps moving while the
    seconds do. A file that takes one model call is that estimate alone. Until one call has finished in this read the usual time is a first guess."""
    if s["running"] and s.get("phase") == 1:
        return _reading_now(s)
    if not (s["running"] and s.get("now")):
        return None
    name, step, detail = s["now"]
    seconds = int(time.monotonic() - s.get("now_since", time.monotonic()))
    percent, estimated, doing = None, False, step
    if step in ("sorting", "reading part"):
        usual = trace.average_seconds(conn, s.get("run", "")) or FIRST_GUESS_SECONDS
        inside = min(0.95, seconds / usual)  # how far through the call being waited for, never quite done
        part = re.search(r"part (\d+) of (\d+)", detail)
        if step == "reading part" and part:
            percent = round(((int(part[1]) - 1) + inside) * 100 / int(part[2]), 1)
            doing = detail  # "reading part 1 of 2"
        else:
            percent = round(inside * 100, 1)
        estimated = True
    return {"name": name, "step": doing, "percent": percent, "estimated": estimated, "seconds": seconds}


def _counted(state: State, conn, s: dict[str, Any]) -> dict[str, Any]:
    """The parts of the status that count through the whole database (the steps, the files waiting, the files just done). Like every count here they are reused for a few seconds and
    brought up to date in the background: a status question must never wait for the database, however big it is or busy a read keeps it."""
    snapshot = {key: s.get(key) for key in ("phase", "run", "now")} | {"rejected": dict(s.get("rejected") or {})}

    def make(c) -> dict[str, Any]:
        return {
            "steps": _steps(c, snapshot),
            "waiting": judging.waiting_files(c, (snapshot.get("now") or ("",))[0]),
            "recent": trace.finished(c, snapshot.get("run") or ""),
        }

    return _cached(f"counted:{snapshot['phase']}", make, state, conn, first={"steps": _steps_for_now(snapshot), "waiting": [], "recent": []})


def _scan_status(state: State, conn, query: dict[str, str]) -> dict:
    s = state.scan
    reading = bool(s["running"] and s.get("phase") == 1)  # step 1 shows the one file being read, nothing about files finished or still to come
    counted = _counted(state, conn, s) if s["running"] else {"recent": [], "waiting": [], "steps": []}
    return {
        "running": s["running"],
        "progress": s["progress"],
        "file": _file_now(s, conn),
        "recent": [] if reading else counted["recent"],
        "waiting": [] if reading else counted["waiting"],
        "steps": counted["steps"],
        "unread_files": [*_unread_files(), *(s.get("rejected_files") or [])][
            :50
        ],  # what the last round could not read stays on the card after the read, until a round reads it
        "summary": s["summary"],
        "problems": s["problems"],
        "needs_check": [],
        "parts": _parts(state, conn),
        "paused": bool(s["running"] and state.control == "pause"),
        "stopping": bool(s["running"] and state.control == "stop"),
    }
