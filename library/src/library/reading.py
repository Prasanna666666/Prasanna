"""The Update: take in what the reader found, sort it, group it, one round at a time."""

from __future__ import annotations

import json
import os
import threading
import time

from kit import log

from . import appstate, bulkmail, concepts, flags, judging, pictures, scanstatus, store, trace
from .appstate import State

SETTLE_SECONDS = 3
AUTO_LIMIT = int(
    os.environ.get("ATLAS_AUTO_LIMIT", "50")
)  # files: automatic reading only when fewer than this are waiting (and a round that starts by itself stops after this many)
JUDGE_PER_ROUND = 20  # judged per round: then the reader's new files are taken in again, so the count keeps moving while the model works


class _StopRequested(Exception):
    """The person pressed Stop while the pictures were being read."""


def _read_pictures(state: State, conn, client, model) -> None:
    """The picture part of an Update: wait for the picture reader, then read photographed receipts and letters like any other document."""
    engine = state.engine()
    if engine is None:
        return
    state.scan["progress"] = "Reading pictures…"

    def progress(message: str) -> None:
        state.scan.update(progress=message)
        if state.control == "stop":
            raise _StopRequested

    try:
        done = pictures.wait_for_scan(engine, progress)
    except _StopRequested:
        return  # stopped while the pictures were being read: the picture reader carries on by itself, nothing more is started here
    state.scan["summary"] += f"; {done}" if done else ""
    index = engine.db.connect()
    try:
        found = store.ingest_pictures(conn, index)  # photographed receipts and letters are read like any other document
    finally:
        index.close()
    if found:
        state.scan["progress"] = f"Reading {found} pictures of documents…"
        judging.judge_pending(conn, client, model, lambda m: state.scan.update(progress=m), lambda: state.control)
        state.scan["summary"] += f"; {found} pictures of documents"


def _finish(state: State, conn, client, model, followed: trace.Trace) -> None:
    """The end of a read: every matter is put together and read in full, then the audit says exactly what, if anything, is left."""
    if client is None or not model or state.control == "stop":
        return
    judging.finish_matters(
        conn, client, model, lambda: state.control, lambda m: state.scan.update(progress=m), followed, phase=lambda n: state.scan.update(phase=n)
    )
    if state.control != "stop":
        state.scan["summary"] += ". " + judging.audit_line(judging.audit(conn))


MAIL_SCOPE_MARK = ".mail-scope"  # holds the rules the mail held here was read under
MAX_READER_ROUNDS = 5  # how often a round that stopped short is asked for again
READER_START_SECONDS = 90  # how long the reader may take to pick up the request before it is called not running


def _round_complete() -> bool:
    """Has the reader gone through every file, mail and attachment it counted? (Each counts once it has been looked at: read, already known, left out or unreadable, so a complete round always reaches the count.)"""
    found, gone, unread = scanstatus._found(), scanstatus._gone_through(), scanstatus._unread()
    if not found or not gone:
        return True  # nothing to compare with: do not hold the read
    return all(gone.get(key, 0) + unread.get(key, 0) >= int(found.get(key) or 0) for key in ("documents", "mails", "attachments"))


def _note_rejected(state: State, name: str, why: str, group: str) -> None:
    """A result the service would not take in is counted as not read, in the group it belongs to, and named with the reason."""
    rejected = state.scan.setdefault("rejected", {})
    rejected[group] = rejected.get(group, 0) + 1
    state.scan.setdefault("rejected_files", []).append(f"{name}: {why}")


def _take_in_all(state: State, conn, totals: dict[str, int]) -> str:
    """Step 1, completely: everything the reader produces is taken in until the reader has picked the request up, finished its round and nothing new arrives. Nothing is sorted meanwhile.
    Returns what went wrong, if anything (the reader never picked the request up)."""
    state.scan["phase"] = appstate.PHASE_READ
    asked = time.monotonic()
    retries, last_gone = 0, 0  # how often the reader was asked again because its round stopped short, and how far it had got
    while True:
        got = (
            store.ingest_dir(
                conn,
                appstate.parsed_dir(),
                lambda: state.control == "stop",
                lambda name: state.scan.setdefault("taken", []).append(name),
                lambda name, why, group: _note_rejected(state, name, why, group),
            )
            if appstate.parsed_dir().is_dir()
            else {"new": 0}
        )
        del state.scan.get("taken", [])[:-3]  # the last few files taken in are all the card shows
        totals["new"] += got["new"]
        totals["replaced"] += got.get("replaced", 0)
        busy = (appstate.parsed_dir() / ".busy").exists()
        waiting = (appstate.parsed_dir() / ".wake").exists()  # the reader has not yet started the round that was asked for
        if state.control == "stop":
            return ""
        if waiting and not busy and time.monotonic() - asked > READER_START_SECONDS:
            return "" if totals["new"] else "The part of Documents that reads your files did not start"
        if not busy and not waiting and not got["new"]:
            gone = sum(scanstatus._gone_through().values())
            if (
                not _round_complete() and retries < MAX_READER_ROUNDS and gone > last_gone
            ):  # the round stopped before it had gone through everything it counted: it is asked again, while it still gets further
                retries, last_gone = retries + 1, gone
                (appstate.parsed_dir() / ".wake").touch()
                asked = time.monotonic()
                continue
            return ""
        state.scan["progress"] = f"Reading… {totals['new']} new files so far"
        if busy or waiting:
            time.sleep(SETTLE_SECONDS)


MAX_SORT_PASSES = 3  # how often files the model could not make sense of are asked again, before grouping starts


def _sort_pass(state: State, conn, client, model, followed: trace.Trace, totals: dict[str, int]) -> str:
    problem = ""
    while state.control != "stop":
        judged = judging.judge_pending(conn, client, model, lambda m: state.scan.update(progress=m), lambda: state.control, JUDGE_PER_ROUND, followed)
        totals["read"] += judged["read"]
        totals["skipped"] += judged["skipped"]
        problem = judged["problem"] or problem
        if judged["stopped"] or not (judged["read"] + judged["skipped"]):
            break
    return problem


def _sort_all(state: State, conn, client, model, followed: trace.Trace, totals: dict[str, int]) -> str:
    """Step 2, completely: the model sorts every file that needs it, in the order the apps are served in, until none is left. A file the model could not make sense of is asked again
    (a smaller question each time) before grouping starts, not only at the next press. Returns what went wrong, if anything."""
    state.scan["phase"] = appstate.PHASE_SORT
    problem = _sort_pass(state, conn, client, model, followed, totals)
    for _ in range(MAX_SORT_PASSES - 1):
        if state.control == "stop" or problem or not store.retry_unclear(conn):
            break
        problem = _sort_pass(state, conn, client, model, followed, totals)
    return problem


def _summarise(state: State, conn, totals: dict[str, int]) -> bool:
    """What the read found, in words, for the panel. Returns True when the rest of the read (pictures, interpretation) should go on: it did not stop and was not cut off by the automatic limit."""
    counts = store.counts(conn)
    new, replaced = totals["new"], totals["replaced"]
    line = f"{new} new file{'s' if new != 1 else ''}, {counts['documents']} in all"
    if replaced:
        line += f"; {replaced} changed file{'s' if replaced != 1 else ''} replaced their older version"
    if state.control == "stop":
        line = "Stopped. " + line + ". Reading carries on from here next time."
    elif (appstate.parsed_dir() / flags.AUTO_CAPPED).exists():
        line += f"; automatic reading stopped at its limit of {AUTO_LIMIT} files: press Read new files for the rest"
    state.scan["summary"] = line
    return state.control != "stop" and not (appstate.parsed_dir() / flags.AUTO_CAPPED).exists()


def _mail_scope() -> str:
    """A fingerprint of the rules for which mail is read (`mailboxes.json`, or LIBRARY_MAILBOXES): when it changes, the mail read under the old rules is forgotten."""
    import hashlib

    rules = json.dumps([sorted(bulkmail.mailboxes_read()), sorted(bulkmail._bulk_headers().items())])
    return hashlib.sha256(rules.encode()).hexdigest()[:16]


def _forget_last_read() -> None:
    """The last read's counts, progress, current file and unreadable files are not this read's: the reader counts again, and until it has the card says counting."""
    for name in (".now", ".found", ".progress", ".unread-files"):
        (appstate.parsed_dir() / name).unlink(missing_ok=True)


def _forget_what_was_read_under_other_rules(conn) -> None:
    """What was read under rules that have since changed is forgotten and read again, once per change: the mail under other rules for which mail is read, the scanned pages when Apple's
    text recognition becomes available, and what had something left out under the old limits."""
    scope, marker = _mail_scope(), appstate.parsed_dir() / MAIL_SCOPE_MARK
    if not marker.exists() or marker.read_text() != scope:
        store.forget_mail(conn, appstate.parsed_dir())
        marker.write_text(scope)
    engine_file = appstate.parsed_dir() / ".ocr-engine"
    engine = engine_file.read_text().strip() if engine_file.exists() else ""
    store.forget_stale_reads(
        conn, appstate.parsed_dir(), engine if engine == "apple" else ""
    )  # whatever was read under other limits, or with a worse text recognition, is read again


def _read_all(state: State) -> None:
    """Update, in three strict stages: everything is read, then everything is sorted, then everything is understood. One press does all of it (and the last stage is bounded; the end of a read says what is left)."""
    conn = state.connect()
    totals = {"new": 0, "read": 0, "skipped": 0, "replaced": 0}
    problem = ""
    try:
        try:
            client, model = appstate.model_client()
        except RuntimeError:
            client, model = None, ""
        if client is not None:
            client = judging.StoppableModel(client, lambda: state.control == "stop")  # Stop ends a wait for the model at once
        followed = trace.Trace(conn, lambda name, step, detail: state.scan.update(now=(name, step, detail), now_since=time.monotonic()))
        state.scan["run"] = followed.run
        appstate.parsed_dir().mkdir(parents=True, exist_ok=True)
        _forget_what_was_read_under_other_rules(conn)
        judging.mark_old_files(conn)  # files sorted before the apps were declared get their marks (on this connection: no other writer is at work meanwhile)
        store.retry_unclear(conn)  # what the model could not make sense of last time gets another try, once per press
        _forget_last_read()
        state.scan.update(rejected={}, rejected_files=[])  # what the service itself would not take in is counted afresh
        (appstate.parsed_dir() / ".wake").touch()
        time.sleep(SETTLE_SECONDS)
        problem = _take_in_all(state, conn, totals)  # step 1, completely
        problem = _sort_all(state, conn, client, model, followed, totals) or problem  # then step 2, completely
        if client is not None and state.control != "stop":
            store.name_kinds(conn, client, model, lambda: state.control)  # the kinds get a few plain names before grouping
            concepts.resolve(
                conn, client, model, lambda: state.control
            )  # and each plain name is decided once: which concept it means to the parts that show files
        if _summarise(state, conn, totals):
            _read_pictures(state, conn, client, model)
            _finish(state, conn, client, model, followed)
        if state.control != "stop":
            store.warm_search(conn, state.picture_text(), lambda: state.control == "stop")
        state.scan["problems"] = [problem] if problem else []
    except judging.Stopped:
        state.scan["summary"] = "Stopped. What was read stays; reading carries on from here next time."
    except Exception as exc:  # noqa: BLE001 - shown on the page and logged, never lost
        log.failed("update failed", exc)
        state.scan["problems"] = [f"{type(exc).__name__}: {exc} (in {log.where(exc)})"]
    finally:
        state.scan.update(running=False, now=None, phase=None)
        scanstatus._CACHE.clear()
        conn.close()


def start_scan(state: State, auto: bool = False) -> bool:
    """Start an Update. A round the person starts reads everything; an automatic one (`auto`) is limited to AUTO_LIMIT files and stops there."""
    with state.lock:
        if state.scan["running"]:
            return False
        state.scan.update(running=True, progress="Starting…", summary="", problems=[])
        state.control = "run"
        appstate.parsed_dir().mkdir(parents=True, exist_ok=True)
        for flag in (".pause", ".stop", flags.AUTO_LIMIT):
            (appstate.parsed_dir() / flag).unlink(missing_ok=True)
        if auto:
            (appstate.parsed_dir() / flags.AUTO_LIMIT).write_text(str(AUTO_LIMIT))
    threading.Thread(target=_read_all, args=(state,), name="update", daemon=True).start()
    return True


def _post_auto(state: State, conn, body: dict) -> dict:
    """A request to read by itself (from the idle check on this computer). It reads only when a small amount is waiting: above the limit it does nothing and says so,
    so a big read is always the person's own decision (the Read new files button)."""
    if state.scan["running"]:
        return {"started": False, "reason": "running"}
    if not scanstatus._found():
        return {"started": False, "reason": "no first read yet: press Read new files once"}
    waiting = scanstatus.backlog(conn)
    if waiting >= AUTO_LIMIT:
        note = (
            f"Automatic reading is waiting for you: {waiting:,} files are unread; automatic reading is only for fewer than {AUTO_LIMIT}. Press Read new files."
        )
        state.scan["summary"] = note
        return {"started": False, "reason": "large", "waiting": waiting, "limit": AUTO_LIMIT}
    return {"started": start_scan(state, auto=True), "reason": "small", "waiting": waiting, "limit": AUTO_LIMIT}  # the round also stops at the limit
