"""A way back from what the assistant adds at once. Every person, date, task, note or event it adds is written down here with the question it was added in. `undo_last_additions` takes back what the latest such question added; like every change that removes something, the assistant only PREPARES it and the person's own yes makes it (changes.py). A whole statement import is not journaled: its payments are removed one by one with `delete_transaction`."""

from __future__ import annotations

import sqlite3
from typing import Any

# the tool that added it -> (table, the column that names it for the person)
TABLES = {
    "add_person": ("people", "name"),
    "add_task": ("tasks", "title"),
    "add_note": ("notes", "title"),
    "create_event": ("events", "name"),
    "add_important_date": ("important_dates", "label"),
}


def record(conn: sqlite3.Connection, tool: str, data: Any, turn: str) -> None:
    """Remember one addition made by the assistant in this question. An event that already existed was not added, so it is not remembered."""
    if tool not in TABLES or not isinstance(data, dict) or not isinstance(data.get("id"), int) or data.get("created") is False:
        return
    table, _ = TABLES[tool]
    conn.execute("INSERT INTO assistant_additions (turn, tool, tbl, row_id) VALUES (?,?,?,?)", (turn, tool, table, data["id"]))
    conn.commit()


def _latest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    newest = conn.execute("SELECT turn FROM assistant_additions WHERE undone=0 ORDER BY id DESC LIMIT 1").fetchone()
    if newest is None:
        return []
    return conn.execute("SELECT * FROM assistant_additions WHERE undone=0 AND turn=? ORDER BY id", (newest["turn"],)).fetchall()


def _name(conn: sqlite3.Connection, row: sqlite3.Row) -> str:
    table, column = TABLES[row["tool"]]
    found = conn.execute(f"SELECT {column} FROM {table} WHERE id=?", (row["row_id"],)).fetchone()
    return str(found[0]) if found else ""


def preview(conn: sqlite3.Connection) -> str:
    """What the next undo would remove, in words, for the person to read before they say yes."""
    names = [f"{TABLES[r['tool']][0].replace('_', ' ')} [{n[:60]}]" for r in _latest(conn) if (n := _name(conn, r))]
    return ", ".join(names)


def undo_last_additions(conn: sqlite3.Connection, a: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remove what the assistant added in its latest question and still exists. A person is removed with their dates (as `delete_person` does)."""
    rows = _latest(conn)
    if not rows:
        return {"removed": 0, "note": "the assistant has added nothing that could be taken back"}
    removed = 0
    for row in rows:
        table, _ = TABLES[row["tool"]]
        if table == "people":
            conn.execute("DELETE FROM important_dates WHERE person_id=?", (row["row_id"],))
        removed += conn.execute(f"DELETE FROM {table} WHERE id=?", (row["row_id"],)).rowcount
        conn.execute("UPDATE assistant_additions SET undone=1 WHERE id=?", (row["id"],))
    conn.commit()
    return {"removed": removed}
