"""Prompt ideas drawn from the user's own library (not a fixed list of canned queries)."""

from __future__ import annotations

import sqlite3

from ..people.repository import named_people


def suggest_prompts(conn: sqlite3.Connection, limit: int = 6) -> list[str]:
    ideas: list[str] = []
    place = conn.execute(
        "SELECT place FROM items WHERE place IS NOT NULL AND missing=0 GROUP BY place ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    if place:
        ideas.append(f"Photos from {place[0].split(',')[0]}")
    people = named_people(conn, 2)
    if people:
        ideas.append(f"Photos of {people[0][1]}")
    if len(people) > 1:
        ideas.append(f"{people[0][1]} and {people[1][1]} together")
    year = conn.execute(
        "SELECT substr(taken_at,1,4) y FROM items WHERE taken_at IS NOT NULL AND missing=0 GROUP BY y ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    if year:
        ideas.append(f"My best sunsets from {year[0]}")
    ideas += ["Group photos taken at night", "Documents that mention an invoice", "Show my blurry photos"]
    return ideas[:limit]
