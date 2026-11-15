"""The trace of a read: every step on every file, written as it happens: which file, what was done to it, what came of it, how many seconds it took. It is how a read is followed
(the panel shows the file being worked on right now) and checked afterwards (`/api/trace`, or the log of the Documents container). Names and steps only, never what a file says."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

KEEP = 30_000  # steps kept: the last few reads in full


class Trace:
    """One read's trace. `now` is told which file is being worked on and how, for the panel."""

    def __init__(self, conn, now: Callable[[str], None] | None = None) -> None:
        self.conn = conn
        self.run = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self._now = now
        self._count = 0
        self._began = time.monotonic()

    def step(self, name: str, step: str, detail: str = "", seconds: float = 0.0) -> None:
        self.conn.execute(
            "INSERT INTO trace (run, at, name, step, detail, seconds) VALUES (?,?,?,?,?,?)",
            (self.run, datetime.now().astimezone().strftime("%H:%M:%S"), name[:200], step, detail[:300], round(seconds, 1)),
        )
        self._count += 1
        if self._count % 200 == 0:
            self.conn.execute("DELETE FROM trace WHERE id <= (SELECT MAX(id) FROM trace) - ?", (KEEP,))
        self.conn.commit()
        print(f"trace {self.run} | {name} | {step} | {detail} | {seconds:.1f}s", flush=True)
        if self._now is not None:
            self._now(f"{name}: {step}" + (f" ({detail})" if detail and step in ("identifying", "reading part") else ""))


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
