"""Family and close people, plus the dates that matter (birthdays, anniversaries, check-ups)."""

from __future__ import annotations

from datetime import date

from .. import dates
from ..db import rows
from ..module import I, Module, S, Tool

MIGRATIONS = (
    """
    CREATE TABLE people (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        relation TEXT NOT NULL DEFAULT '',   -- mother, father, spouse, friend...
        about TEXT NOT NULL DEFAULT ''       -- health notes, preferences, anything useful
    );
    CREATE TABLE important_dates (
        id INTEGER PRIMARY KEY,
        person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        label TEXT NOT NULL,
        month INTEGER NOT NULL, day INTEGER NOT NULL,
        year INTEGER                          -- original year, if known (for ages / anniversaries)
    );
    """,
)


def add_person(conn, a):
    cur = conn.execute("INSERT INTO people (name, relation, about) VALUES (?,?,?)",
                       (a["name"].strip(), a.get("relation", ""), a.get("about", "")))
    conn.commit()
    return {"id": cur.lastrowid}


def list_people(conn, a):
    return rows(conn.execute("SELECT * FROM people ORDER BY name"))


def update_person(conn, a):
    p = conn.execute("SELECT * FROM people WHERE id=?", (a["id"],)).fetchone()
    if p is None:
        raise ValueError(f"no person {a['id']}")
    conn.execute("UPDATE people SET name=?, relation=?, about=? WHERE id=?",
                 (a.get("name", p["name"]), a.get("relation", p["relation"]), a.get("about", p["about"]), p["id"]))
    conn.commit()
    return {"id": p["id"]}


def add_important_date(conn, a):
    d = date.fromisoformat(a["date"])
    keep_year = d.year if a.get("year_known", True) and d.year > 1 else None
    cur = conn.execute("INSERT INTO important_dates (person_id, label, month, day, year) VALUES (?,?,?,?,?)",
                       (a["person_id"], a.get("label", "Birthday"), d.month, d.day, keep_year))
    conn.commit()
    return {"id": cur.lastrowid}


def upcoming(conn, today: date, days: int = 30):
    out = []
    for r in conn.execute(
        "SELECT d.*, p.name, p.relation FROM important_dates d JOIN people p ON p.id=d.person_id"
    ):
        try:
            nxt = date(today.year, r["month"], r["day"])
        except ValueError:  # 29 Feb in a non-leap year
            nxt = date(today.year, 3, 1)
        if nxt < today:
            nxt = dates.add_months(nxt.replace(day=1), 12).replace(day=min(r["day"], 28))
        if (nxt - today).days <= days:
            out.append({"name": r["name"], "relation": r["relation"], "label": r["label"], "on": nxt.isoformat(),
                        "in_days": (nxt - today).days, "turning": nxt.year - r["year"] if r["year"] else None})
    return sorted(out, key=lambda x: x["in_days"])


def upcoming_dates(conn, a):
    return upcoming(conn, date.today(), int(a.get("days", 30)))


def delete_person(conn, a):
    conn.execute("DELETE FROM people WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


MODULE = Module(
    "people",
    MIGRATIONS,
    (
        Tool("add_person", "Add a family member or someone close.",
             {"name": S("Name"), "relation": S("mother, father, wife, son, friend..."), "about": S("Useful notes")},
             add_person, ("name",)),
        Tool("list_people", "List everyone, with ids.", {}, list_people),
        Tool("update_person", "Edit a person.", {"id": I("Person id"), "name": S("Name"),
             "relation": S("Relation"), "about": S("Notes")}, update_person, ("id",)),
        Tool("add_important_date", "Remember a yearly date (birthday, anniversary...). Use year 0001 if the year is unknown.",
             {"person_id": I("Person id"), "label": S("Birthday, Anniversary..."), "date": S("YYYY-MM-DD")},
             add_important_date, ("person_id", "date")),
        Tool("upcoming_dates", "Birthdays/anniversaries coming up.", {"days": I("Look-ahead, default 30")}, upcoming_dates),
        Tool("delete_person", "Delete a person and their dates.", {"id": I("Person id")}, delete_person, ("id",)),
    ),
)
