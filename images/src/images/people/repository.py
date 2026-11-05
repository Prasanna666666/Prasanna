"""Queries and edits for people and faces."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np

from ..db import in_clause
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


@dataclass(frozen=True)
class FaceReview:
    face_id: int
    item_id: int
    crop: str | None
    similarity: float


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


def rename_person(conn: sqlite3.Connection, person_id: int, name: str) -> None:
    conn.execute("UPDATE people SET name=? WHERE id=?", (name.strip() or None, person_id))
    conn.commit()


def hide_person(conn: sqlite3.Connection, person_id: int) -> None:
    conn.execute("UPDATE people SET hidden=1 WHERE id=?", (person_id,))
    conn.commit()


def merge_people(conn: sqlite3.Connection, keep: int, merge: int) -> None:
    if keep == merge:
        return
    k = conn.execute("SELECT name FROM people WHERE id=?", (keep,)).fetchone()
    m = conn.execute("SELECT name FROM people WHERE id=?", (merge,)).fetchone()
    if k and m and not k["name"] and m["name"]:
        conn.execute("UPDATE people SET name=? WHERE id=?", (m["name"], keep))
    conn.execute("UPDATE faces SET person_id=? WHERE person_id=?", (keep, merge))
    conn.execute("DELETE FROM people WHERE id=?", (merge,))
    conn.commit()


def reject_face(conn: sqlite3.Connection, face_id: int) -> None:
    """'This is not that person': detach and never auto-assign it again."""
    conn.execute("UPDATE faces SET person_id=NULL, locked=1 WHERE id=?", (face_id,))
    conn.commit()


def person_item_ids(conn: sqlite3.Connection, person_ids: list[int]) -> np.ndarray:
    """Ids of photos containing ANY of the given people (all matches, no limit)."""
    if not person_ids:
        return np.zeros(0, np.int64)
    rows = conn.execute(
        f"SELECT DISTINCT f.item_id FROM faces f JOIN items i ON i.id=f.item_id AND i.missing=0 "
        f"WHERE f.person_id IN ({in_clause(person_ids)})",
        person_ids,
    ).fetchall()
    return np.array(sorted(r[0] for r in rows), np.int64)


def items_with_all_people(conn: sqlite3.Connection, person_ids: list[int]) -> np.ndarray:
    """Photos in which ALL the given people appear together."""
    if not person_ids:
        return np.zeros(0, np.int64)
    rows = conn.execute(
        f"SELECT f.item_id FROM faces f JOIN items i ON i.id=f.item_id AND i.missing=0 "
        f"WHERE f.person_id IN ({in_clause(person_ids)}) "
        f"GROUP BY f.item_id HAVING COUNT(DISTINCT f.person_id)=?",
        (*person_ids, len(person_ids)),
    ).fetchall()
    return np.array(sorted(r[0] for r in rows), np.int64)


def faces_for_review(conn: sqlite3.Connection, person_id: int, limit: int = 24) -> list[FaceReview]:
    """A person's faces, least typical first - the likeliest mistakes surface at the top."""
    rows = conn.execute("SELECT id, item_id, crop, emb FROM faces WHERE person_id=?", (person_id,)).fetchall()
    if not rows:
        return []
    matrix = np.vstack([np.frombuffer(r["emb"], np.float32) for r in rows])
    centre = matrix.mean(0)
    centre /= max(float(np.linalg.norm(centre)), 1e-9)
    sims = matrix @ centre
    return [FaceReview(rows[i]["id"], rows[i]["item_id"], rows[i]["crop"], float(sims[i])) for i in np.argsort(sims)[:limit]]


def faces_in_item(conn: sqlite3.Connection, item_id: int) -> list[tuple[str | None, str]]:
    """(crop path, person label) for each face in one photo."""
    rows = conn.execute(
        "SELECT f.crop, p.name, p.id AS pid FROM faces f LEFT JOIN people p ON p.id=f.person_id WHERE f.item_id=?",
        (item_id,),
    ).fetchall()
    return [(r["crop"], r["name"] or (f"Person {r['pid']}" if r["pid"] else "unassigned")) for r in rows]
