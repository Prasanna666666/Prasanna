"""Free-form notes with tags and simple search."""

from __future__ import annotations

from ..db import rows
from ..module import I, Module, S, Tool

MIGRATIONS = (
    """
    CREATE TABLE notes (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '',     -- comma separated, lowercase
        person_id INTEGER,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
)


def _tags(s: str) -> str:
    return ",".join(sorted({t.strip().lower().lstrip("#") for t in s.split(",") if t.strip()}))


def add_note(conn, a):
    cur = conn.execute(
        "INSERT INTO notes (title, body, tags, person_id) VALUES (?,?,?,?)",
        (a.get("title", "").strip(), a["body"], _tags(a.get("tags", "")), a.get("person_id")),
    )
    conn.commit()
    return {"id": cur.lastrowid}


def search_notes(conn, a):
    where, args = [], []
    for word in a.get("query", "").split():
        where.append("(title LIKE ? OR body LIKE ?)")
        args += [f"%{word}%"] * 2
    if a.get("tag"):
        where.append("(',' || tags || ',') LIKE ?")
        args.append(f"%,{a['tag'].lower().lstrip('#')},%")
    sql = "SELECT * FROM notes" + (" WHERE " + " AND ".join(where) if where else "")
    return rows(conn.execute(sql + " ORDER BY updated DESC, id DESC LIMIT ?", [*args, int(a.get("limit", 20))]))


def update_note(conn, a):
    n = conn.execute("SELECT * FROM notes WHERE id=?", (a["id"],)).fetchone()
    if n is None:
        raise ValueError(f"no note {a['id']}")
    conn.execute(
        "UPDATE notes SET title=?, body=?, tags=?, updated=CURRENT_TIMESTAMP WHERE id=?",
        (a.get("title", n["title"]), a.get("body", n["body"]),
         _tags(a["tags"]) if "tags" in a else n["tags"], n["id"]),
    )
    conn.commit()
    return {"id": n["id"]}


def delete_note(conn, a):
    conn.execute("DELETE FROM notes WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


MODULE = Module(
    "notes",
    MIGRATIONS,
    (
        Tool("add_note", "Save a note.", {"body": S("Note text"), "title": S("Optional title"),
             "tags": S("Comma separated tags"), "person_id": I("Related person id")}, add_note, ("body",)),
        Tool("search_notes", "Find notes by words (all must match) and/or tag. Empty query lists recent notes.",
             {"query": S("Words to look for"), "tag": S("Tag"), "limit": I("Max rows")}, search_notes),
        Tool("update_note", "Edit a note (only the given fields change).",
             {"id": I("Note id"), "title": S("New title"), "body": S("New body"), "tags": S("New tags")},
             update_note, ("id",)),
        Tool("delete_note", "Delete a note permanently.", {"id": I("Note id")}, delete_note, ("id",)),
    ),
)
