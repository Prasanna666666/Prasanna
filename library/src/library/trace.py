"""The trace of a read: every step on every file, written as it happens: which file, what was done to it, what came of it, how many seconds it took. It is how a read is followed
(the panel shows the file being worked on right now) and checked afterwards (`/api/trace`, or the log of the Documents container). Names and steps only, never what a file says."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

KEEP = 30_000  # steps kept: the last few reads in full


class Trace:
    """One read's trace. `now` is told which file is being worked on, the step and its detail, for the panel."""

    def __init__(self, conn, now: Callable[[str, str, str], None] | None = None) -> None:
        self.conn = conn
        self.run = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self._now = now
        self._count = 0
        self._began = time.monotonic()

    def step(self, name: str, step: str, detail: str = "", seconds: float = 0.0) -> None:
        for attempt in range(5):
            try:
                self.conn.execute(
                    "INSERT INTO trace (run, at, name, step, detail, seconds) VALUES (?,?,?,?,?,?)",
                    (self.run, datetime.now().astimezone().strftime("%H:%M:%S"), name[:200], step, detail[:300], round(seconds, 1)),
                )
                self._count += 1
                if self._count % 200 == 0:
                    self.conn.execute("DELETE FROM trace WHERE id <= (SELECT MAX(id) FROM trace) - ?", (KEEP,))
                self.conn.commit()
                break
            except (
                sqlite3.OperationalError
            ):  # the database was busy: the trace is for looking at, so it waits a moment and, failing that, leaves this line out rather than stop the read
                time.sleep(0.2 * (attempt + 1))
        print(f"trace {self.run} | {name} | {step} | {detail} | {seconds:.1f}s", flush=True)
        if self._now is not None:
            self._now(name, step, detail)


FAILED = "could not be sorted"
FAILED_GROUP = "could not be read"
SHOWN = (
    "sorted",
    FAILED,
    FAILED_GROUP,
    "group read",
    "kept as sorted",
)  # what the card lists: files a model worked on; a file with nothing to read is not news
FINISHED = ("sorted", "skipped", FAILED, FAILED_GROUP, "group read", "kept as sorted")


def _what_it_is(conn, name: str) -> str:
    """What the model called the file, in its own words (its title), looked up when it is shown; the trace itself never holds what a file says."""
    row = conn.execute("SELECT facts FROM documents WHERE name=? AND judged=1 ORDER BY id DESC LIMIT 1", (name,)).fetchone()
    try:
        facts = json.loads(row["facts"]) if row and row["facts"] else {}
    except ValueError:
        return ""
    return str(facts.get("title") or "")[:70] if isinstance(facts, dict) else ""


def finished(conn, run: str, limit: int = 5) -> list[dict[str, str]]:
    """The last files finished in this read, newest first, each with its result, how long it took and whether it worked (`state`: done or failed), for the panel.
    A file that was sorted is described by its title, not by the category the apps route it by."""
    rows = conn.execute(
        f"SELECT name, step, detail, seconds FROM trace WHERE run=? AND step IN ({','.join('?' for _ in SHOWN)}) ORDER BY id DESC LIMIT ?",
        (run, *SHOWN, limit),
    )
    out = []
    for r in rows:
        detail = (_what_it_is(conn, r["name"]) or r["detail"]) if r["step"] == "sorted" else r["detail"]
        out.append(
            {
                "name": r["name"],
                "state": "failed" if r["step"] in (FAILED, FAILED_GROUP) else "done",
                "detail": r["step"] + (f": {detail}" if detail else "") + (f" ({r['seconds']:.0f} s)" if r["seconds"] >= 1 else ""),
            }
        )
    return out


def average_seconds(conn, run: str) -> float:
    """How long sorting one file has taken in this read so far (0 until there is one to go by)."""
    row = conn.execute("SELECT AVG(seconds) FROM trace WHERE run=? AND step='sorted' AND seconds>=1", (run,)).fetchone()
    return float(row[0] or 0)


def recent(conn, run: str = "", name: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """The newest steps of a read (the latest read unless `run` is given), newest first; `name` keeps only the steps of files whose name contains it."""
    if not run:
        row = conn.execute("SELECT run FROM trace ORDER BY id DESC LIMIT 1").fetchone()
        run = row["run"] if row else ""
    rows = conn.execute(
        "SELECT run, at, name, step, detail, seconds FROM trace WHERE run=? AND name LIKE ? ORDER BY id DESC LIMIT ?",
        (run, f"%{name}%", max(1, min(limit, 500))),
    )
    return [dict(r) for r in rows]
