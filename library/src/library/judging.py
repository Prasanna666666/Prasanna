"""Judging: what the model makes of each read file (sort, name, finish), one pass at a time."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from kit import extract
from kit.text import json_object
from kit.units import SECONDS_PER_HOUR, SECONDS_PER_MINUTE

from . import apps, appstate, casebook, priority, recognise, relevance, store
from .trace import FAILED, Hooks, Trace

# ---- judging: what is each document? ------------------------------------------------------------------------------------------
MIN_CALLS_FOR_SPEED = 2  # the speed of the model is quoted only after this many answers


def _mark_ready(conn, sha: str, judged: int, facts: dict | None) -> None:
    conn.execute(
        "UPDATE documents SET judged=?, facts=?, ready=(SELECT COALESCE(MAX(ready),0)+1 FROM documents) WHERE sha256=?",
        (judged, json.dumps(facts) if facts else "", sha),
    )


def _data(d) -> dict:
    return json_object(d["data"])


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


def _understand(client, model: str, d, progress: store.Progress | None = None) -> dict:
    """What the model makes of one document: what it is and its key facts, and for a medical document the lab values and medicines the document itself prints."""
    facts = extract.classify(
        client, model, d["name"], d["text"], apps.describe()
    )  # every file gets the full reading: what it is, which apps it is about, and its details checked against the text
    readers = {
        apps.reading(name) for name in [*facts.get("apps", []), d["area"]]
    }  # an app can ask for an extra reading of its files (a folder named after the app counts too)
    if "medical" in readers:
        facts["health"] = extract.medical_details(client, model, d["name"], d["text"], progress)
    return facts


def _trace(trace: Trace | None, name: str, step: str, detail: str = "", seconds: float = 0.0) -> None:
    if trace is not None:
        trace.step(name, step, detail, seconds)


def _both(progress: store.Progress | None, trace: Trace | None, name: str) -> store.Progress:
    """The progress of one long reading (the parts of a medical document) goes to the panel and into the trace."""

    def say(message: str) -> None:
        if progress:
            progress(message)
        _trace(trace, name, "reading part", message.rsplit(": ", 1)[-1])

    return say


def _identify_one(conn, client, model, d, progress: store.Progress | None, trace: Trace | None, ahead: _Ahead) -> tuple[str, str]:
    """The model identifies one file and the result is saved at once (the counts in the panel change with every file, not every twentieth).
    Returns "ok", "unclear" (answered but unusable: counted and tried again at the next read) or "unreachable" with the reason."""
    _trace(trace, d["name"], "sorting", f"{len(d['text']):,} characters")
    started = time.monotonic()
    try:
        facts = ahead.result(d, _both(progress, trace, d["name"]))
    except extract.Unclear as why:
        conn.execute("UPDATE documents SET judged=3, tries=tries+1 WHERE sha256=?", (d["sha256"],))
        tries = conn.execute("SELECT tries FROM documents WHERE sha256=?", (d["sha256"],)).fetchone()[0]
        _trace(trace, d["name"], FAILED, f"{why}; it is tried again at the next read (try {tries} of {store.MAX_TRIES})", time.monotonic() - started)
        conn.commit()
        return "unclear", ""
    except Stopped:
        return "stopped", ""
    except RuntimeError as exc:
        return "unreachable", str(exc)
    _mark_ready(conn, d["sha256"], 1, facts)
    _trace(trace, d["name"], "sorted", f"{facts.get('kind', 'other')}", time.monotonic() - started)
    conn.commit()
    return "ok", ""


def _duration(seconds: float) -> str:
    hours, rest = divmod(int(seconds), SECONDS_PER_HOUR)
    return f"{hours} h {rest // SECONDS_PER_MINUTE} min" if hours else f"{rest // SECONDS_PER_MINUTE} min" if rest >= SECONDS_PER_MINUTE else f"{rest} s"


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
    if calls < MIN_CALLS_FOR_SPEED:
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


def _skippable(d) -> bool:
    """Nothing readable to ask the model about: the file stays, found by its name."""
    if d["kind"] == "binary" or not d["text"].strip():
        return True
    if d["kind"] == "email" and _attachment_count(d) > 0:
        return False  # its attachments are read, and what the mail says about them (who sent it, when it is due) is what makes them mean something
    # The keyword gate exists to keep thousands of newsletters away from a small model: it applies to the text of an email and to the words read from a picture, never to a file or an attachment
    return (d["kind"] == "email" or d["area"] == "pictures") and not relevance.worth_reading(d["name"], "email", d["text"])


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

    def result(self, d, say: store.Progress) -> dict:
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
    conn, client, model, progress: store.Progress | None = None, control: Callable[[], str] | None = None, limit: int = 0, trace: Trace | None = None
) -> dict[str, Any]:
    """Judge every document not yet judged (or `limit` of them: the caller comes back for more, so new files keep being taken in meanwhile). Files from a collection folder you named, and anything else with text worth reading, go to the model; the rest is marked and left alone.
    If the model cannot be reached the document stays as it is and the next round tries again."""
    total = conn.execute("SELECT COUNT(*) FROM documents WHERE judged=0").fetchone()[0]
    out: dict[str, Any] = {"read": 0, "skipped": 0, "waiting": 0, "unclear": 0, "problem": "", "stopped": False}
    began = time.monotonic()
    ahead = _Ahead(client, model)
    try:
        return _judge_chunks(conn, client, model, Hooks(control, progress, trace), limit, _Pass(out, total, ahead, began))
    finally:
        ahead.close()


def _ask_model(conn, client, model, hooks: Hooks, this: _Pass, where: tuple, calls: int) -> str:
    """Ask the model about one document. Says what came of it: "" (answered), "waiting" (no model to ask), "unclear" (no usable answer), "stopped" (the person pressed Stop) or "unreachable"."""
    chunk, position, d = where
    out = this.out
    if client is None or not model:
        out["waiting"] += 1
        out["problem"] = "The local model is not running, so new files cannot be read yet. Start Ollama and press Read new files again."
        return "waiting"
    if hooks.progress:
        hooks.progress(_speed_line(model_work_left(conn), time.monotonic() - this.began, calls))
    this.ahead.prefetch(chunk, position)
    result, problem = _identify_one(conn, client, model, d, hooks.progress, hooks.trace, this.ahead)
    if result == "unreachable":
        out["problem"] = problem
    if result == "unclear":
        out["unclear"] += 1
    if result in ("stopped", "unclear", "unreachable"):
        return result
    if PARALLEL == 1:
        time.sleep(
            store.GENTLE_SECONDS
        )  # a short rest after each model call, only when one is asked at a time: with two in flight the model is never left idle
    return ""


@dataclass
class _Pass:
    """One pass over the waiting files: what it has done so far, how many there were, the model call that runs ahead, and when it began."""

    out: dict[str, Any]
    total: int
    ahead: _Ahead
    began: float


def _judge_chunks(conn, client, model, hooks: Hooks, limit: int, this: _Pass) -> dict[str, Any]:
    out, total = this.out, this.total
    control, trace = hooks.control, hooks.trace
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
            elif _skippable(d):  # nothing readable to ask the model about: it stays, found by its name
                why = _why_skipped(d)
                _mark_ready(conn, d["sha256"], 2, {"skipped": why})  # the reason is kept, so what was not shown to the model can be counted and read later
                _trace(trace, d["name"], "skipped", why)
                out["skipped"] += 1
                continue
            else:
                step = _ask_model(conn, client, model, hooks, this, (chunk, position, d), calls)
                if step != "waiting":
                    calls += 1  # a call to the model was made
                if step in ("waiting", "unclear"):
                    continue
                if step == "stopped":
                    out["stopped"] = True
                    out["waiting"] = total - index + 1
                    conn.commit()
                    return out
                if step == "unreachable":  # the model could not be reached: nothing is marked as done
                    out["waiting"] = total - index + 1
                    conn.commit()
                    return _with_health(conn, client, model, control, out, skip=True)
            out["read"] += 1
            if index % 20 == 0:
                conn.commit()
        conn.commit()
    return _with_health(conn, client, model, control, out)


def _with_health(conn, client, model, control, out: dict[str, Any], skip: bool = False) -> dict[str, Any]:
    if not skip and client is not None and model and not out["stopped"]:
        out["health_filled"] = fill_health_details(conn, client, model, control)
    return out


def finish_matters(conn, client, model, hooks: Hooks | None = None, pairs: int = casebook.MAX_CONFIRMS, groups: int = casebook.MAX_READ_PER_PRESS) -> int:
    """Interpretation: the files are grouped (comparing up to `pairs` pairs) and then up to `groups` groups are read. Done in small slices while files are still being identified,
    and in full at the end of a read. Respects Pause and Stop; what is not reached (the model is slow) is counted by `audit` and carried on. Returns how many groups were read."""
    hooks = hooks or Hooks()
    if hooks.phase:
        hooks.phase(appstate.PHASE_GROUP)
    if hooks.progress:
        hooks.progress("Finding which files belong together…")
    casebook.rebuild(conn, client, model, hooks, pairs)
    if hooks.phase:
        hooks.phase(appstate.PHASE_FINISH)
    done = casebook.understand_pending(conn, client, model, limit=groups, control=hooks.control, progress=hooks.progress, trace=hooks.trace)
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
    """Medical documents judged before lab values and medicines were read, read by the older capped reader, or read only in part get them (again) now; returns how many."""
    clause, args = _apps_clause(apps.with_reading("medical"))
    rows = conn.execute(
        f"SELECT sha256, name, text, facts FROM documents WHERE judged=1 AND {clause} AND facts<>'' AND COALESCE(json_extract(facts, '$.health.complete'), 0) = 0",
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
