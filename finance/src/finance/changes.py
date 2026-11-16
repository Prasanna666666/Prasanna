"""Changes to the money records that the assistant proposes. The assistant can only PREPARE one: it is kept here, waiting, and happens only when the person's own next message is a
short yes, within a few minutes, once. The model cannot confirm anything, because the person's words come from the person's message and never from a tool, a document or the model.
Every proposal and what became of it is kept as the audit trail (`assistant_changes`)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from kit import consent

from . import toolrun
from .modules import ALL
from .modules import tools as registry

CONFIRM_WINDOW_MINUTES = 10  # a yes counts for a change prepared this recently; after that it is asked again
SUMMARY_VALUE_CHARS = 80
SUMMARY_CHARS = 400
STATES = ("waiting", "running", "done", "failed", "superseded", "expired")


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def summarize(name: str, args: dict[str, Any]) -> str:
    """What the change would do, in plain words made by code from the tool's own description and the arguments (never written by the model)."""
    tool = registry(ALL)[name]
    what = tool.description.split(".")[0].strip()
    given = ", ".join(f"{k}: {str(v)[:SUMMARY_VALUE_CHARS]}" for k, v in sorted(args.items()) if v not in (None, ""))
    return (f"{what} ({given})" if given else what)[:SUMMARY_CHARS]


class _Rehearsal:
    """A connection that does everything the real one does except commit: a tool run through it can be checked for errors and then rolled back, leaving the records untouched."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def commit(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _rehearse(conn: sqlite3.Connection, name: str, args: dict[str, Any]) -> str:
    """The tool's own error for these arguments, or '' if it would work. Runs the real tool code, then undoes everything."""
    conn.commit()
    try:
        out, failed = toolrun.run_tool(cast(sqlite3.Connection, _Rehearsal(conn)), name, args)
    finally:
        conn.rollback()
    return str(json.loads(out).get("error", "")) if failed else ""


def stage(conn: sqlite3.Connection, name: str, args: Any, turn: str, asked: str, now: datetime | None = None) -> dict[str, Any]:
    """Keep a change the assistant asked for, waiting for the person's yes. Nothing about the records is changed. An older change that still waits is replaced by this one."""
    given = args if isinstance(args, dict) else {}
    error = _rehearse(conn, name, given)
    if error:
        return {"ok": False, "data": None, "error": error}  # the model is told at once, so it can correct the arguments; nothing is kept
    summary = summarize(name, given)
    moment = now or _now()
    conn.execute("UPDATE assistant_changes SET state='superseded', decided=? WHERE state='waiting'", (_stamp(moment),))
    cur = conn.execute(
        "INSERT INTO assistant_changes (tool, args, summary, turn, asked, created, state) VALUES (?,?,?,?,?,?, 'waiting')",
        (name, json.dumps(given, default=str), summary, turn, asked[:500], _stamp(moment)),
    )
    conn.commit()
    note = f"Waiting for your yes: {summary}. Nothing has been changed yet."
    return {
        "ok": True,
        "data": {"prepared": True, "changed_anything": False, "waiting_for_the_person": summary},
        "error": "",
        "notes": [note],
        "id": cur.lastrowid,
    }


def _expire(conn: sqlite3.Connection, moment: datetime) -> None:
    cutoff = _stamp(moment - timedelta(minutes=CONFIRM_WINDOW_MINUTES))
    conn.execute("UPDATE assistant_changes SET state='expired', decided=? WHERE state='waiting' AND created < ?", (_stamp(moment), cutoff))


def confirm(conn: sqlite3.Connection, user_text: str, turn: str, now: datetime | None = None) -> dict[str, Any]:
    """Apply the waiting change if, and only if, the person's message is a short yes, the change was prepared in an earlier question and recently. At most once: the change is
    claimed before it runs, so a second yes finds nothing waiting."""
    if not consent.confirms(user_text):
        return {"ok": True, "done": False}
    moment = now or _now()
    _expire(conn, moment)
    row = conn.execute("SELECT * FROM assistant_changes WHERE state='waiting' AND turn<>? ORDER BY id DESC LIMIT 1", (turn,)).fetchone()
    if row is None:
        conn.commit()
        return {"ok": True, "done": False}
    claimed = conn.execute("UPDATE assistant_changes SET state='running', decided=? WHERE id=? AND state='waiting'", (_stamp(moment), row["id"]))
    conn.commit()
    if claimed.rowcount != 1:
        return {"ok": True, "done": False}
    out, failed = toolrun.run_tool(conn, row["tool"], json.loads(row["args"]))
    conn.execute("UPDATE assistant_changes SET state=?, outcome=? WHERE id=?", ("failed" if failed else "done", out[: SUMMARY_CHARS * 5], row["id"]))
    conn.commit()
    return {"ok": True, "done": not failed, "failed": failed, "summary": row["summary"], "error": "" if not failed else "the change could not be made"}


def history(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """What the assistant proposed and what became of each, newest first."""
    cur = conn.execute("SELECT id, tool, summary, asked, created, decided, state FROM assistant_changes ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(zip([c[0] for c in cur.description], r, strict=True)) for r in cur.fetchall()]
