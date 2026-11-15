"""Queries and edits for people and faces."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..search.textnorm import tokens


@dataclass(frozen=True)
class PersonSummary:
    id: int
    name: str | None
    photos: int
    faces: int
    cover: str | None  # face crop path relative to the data folder

    @property
    def label(self) -> str:
        return self.name or f"Person {self.id}"


def list_people(conn: sqlite3.Connection, min_photos: int = 2) -> list[PersonSummary]:
    rows = conn.execute(
        "SELECT p.id, p.name, COUNT(f.id) AS n_faces, COUNT(DISTINCT f.item_id) AS n_items, "
        "(SELECT crop FROM faces WHERE person_id=p.id ORDER BY score*px DESC LIMIT 1) AS cover "
        "FROM people p JOIN faces f ON f.person_id=p.id JOIN items i ON i.id=f.item_id AND i.missing=0 "
        "WHERE p.hidden=0 GROUP BY p.id HAVING n_items>=? ORDER BY (p.name IS NULL), n_items DESC",
        (min_photos,),
    ).fetchall()
    return [PersonSummary(r["id"], r["name"], r["n_items"], r["n_faces"], r["cover"]) for r in rows]


def named_people(conn: sqlite3.Connection, limit: int = 200) -> list[tuple[int, str]]:
    rows = conn.execute(
        "SELECT id, name FROM people WHERE name IS NOT NULL AND hidden=0 ORDER BY name LIMIT ?", (limit,)
    ).fetchall()
    return [(r["id"], r["name"]) for r in rows]


def resolve_name(conn: sqlite3.Connection, query: str) -> list[int]:
    """Person ids whose name contains *every* word of ``query`` (case/accent-insensitive).

    ``"anna"`` matches "Anna Smith"; ``"Anna Jones"`` does not match "Anna Smith"."""
    wanted = tokens(query)
    if not wanted:
        return []
    matches = []
    for person_id, name in named_people(conn, limit=100_000):
        if set(wanted) <= set(tokens(name)):
            matches.append(person_id)
    return matches
