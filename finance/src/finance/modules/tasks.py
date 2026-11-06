"""Tasks and reminders: one table; a task with a due date is a reminder. Supports recurrence."""

from __future__ import annotations

from datetime import date

from kit.module import INT, Module, S, Tool

from .. import dates
from ..db import rows

MIGRATIONS = (
    """
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        due TEXT,                         -- 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM'
        recurrence TEXT NOT NULL DEFAULT 'none',
        done INTEGER NOT NULL DEFAULT 0,
        person_id INTEGER,                -- optional link to people.id
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX tasks_due ON tasks(done, due);
    """,
)
RECURRENCES = ["none", "daily", "weekly", "monthly", "yearly"]


def add_task(conn, a):
    due, rec = a.get("due"), a.get("recurrence", "none")
    if due:
        dates.parse(due)  # validate
    if rec not in RECURRENCES:
        raise ValueError(f"recurrence must be one of {RECURRENCES}")
    cur = conn.execute(
        "INSERT INTO tasks (title, due, recurrence, person_id) VALUES (?,?,?,?)",
        (a["title"].strip(), due, rec, a.get("person_id")),
    )
    conn.commit()
    return {"id": cur.lastrowid, "title": a["title"], "due": due, "recurrence": rec}


def list_tasks(conn, a):
    status, where, args = a.get("status", "open"), [], []
    if status == "open":
        where.append("done=0")
    elif status == "done":
        where.append("done=1")
    if a.get("due_on_or_before"):
        where.append("due IS NOT NULL AND substr(due,1,10) <= ?")
        args.append(a["due_on_or_before"])
    sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY due IS NULL, due, id LIMIT ?"
    return rows(conn.execute(sql, [*args, int(a.get("limit", 50))]))


def complete_task(conn, a):
    t = conn.execute("SELECT * FROM tasks WHERE id=?", (a["id"],)).fetchone()
    if t is None:
        raise ValueError(f"no task {a['id']}")
    conn.execute("UPDATE tasks SET done=1 WHERE id=?", (t["id"],))
    nxt = dates.next_occurrence(t["due"], t["recurrence"]) if t["due"] else None
    out = {"completed": t["id"], "next": None}
    if nxt:
        cur = conn.execute(
            "INSERT INTO tasks (title, due, recurrence, person_id) VALUES (?,?,?,?)",
            (t["title"], nxt, t["recurrence"], t["person_id"]),
        )
        out["next"] = {"id": cur.lastrowid, "due": nxt}
    conn.commit()
    return out


def reschedule_task(conn, a):
    dates.parse(a["due"])
    n = conn.execute("UPDATE tasks SET due=? WHERE id=?", (a["due"], a["id"])).rowcount
    conn.commit()
    if not n:
        raise ValueError(f"no task {a['id']}")
    return {"id": a["id"], "due": a["due"]}


def delete_task(conn, a):
    conn.execute("DELETE FROM tasks WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


def overdue_and_today(conn, today: date):
    t = today.isoformat()
    return rows(conn.execute("SELECT * FROM tasks WHERE done=0 AND due IS NOT NULL AND substr(due,1,10) <= ? ORDER BY due", (t,)))


MODULE = Module(
    "tasks",
    MIGRATIONS,
    (
        Tool(
            "add_task",
            "Create a task or reminder. Give `due` to make it a reminder.",
            {
                "title": S("What to do"),
                "due": S("YYYY-MM-DD or YYYY-MM-DDTHH:MM"),
                "recurrence": S("How it repeats", enum=RECURRENCES),
                "person_id": INT("Related person id"),
            },
            add_task,
            ("title",),
        ),
        Tool(
            "list_tasks",
            "List tasks, soonest due first.",
            {
                "status": S("open (default), done or all", enum=["open", "done", "all"]),
                "due_on_or_before": S("YYYY-MM-DD; use for 'what is due today/this week'"),
                "limit": INT("Max rows"),
            },
            list_tasks,
        ),
        Tool("complete_task", "Mark a task done. Recurring tasks automatically schedule the next one.", {"id": INT("Task id")}, complete_task, ("id",)),
        Tool("reschedule_task", "Change a task's due date.", {"id": INT("Task id"), "due": S("New due")}, reschedule_task, ("id", "due")),
        Tool("delete_task", "Delete a task permanently.", {"id": INT("Task id")}, delete_task, ("id",)),
    ),
)
