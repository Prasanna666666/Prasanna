"""Albums that make themselves: runs of photos taken close together in time, named by place and date."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

import numpy as np

GAP_HOURS = 10  # a gap longer than this starts a new album
MIN_PHOTOS = 8


@dataclass(frozen=True)
class Album:
    ids: np.ndarray
    start: str  # ISO date
    end: str
    place: str

    @property
    def title(self) -> str:
        span = self.start if self.start == self.end else f"{self.start} to {self.end}"
        return f"{self.place} - {span}" if self.place else span

    def __len__(self) -> int:
        return len(self.ids)


def _hours_between(a: str, b: str) -> float:
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        return (datetime.strptime(b[:19], fmt) - datetime.strptime(a[:19], fmt)).total_seconds() / 3600
    except ValueError:
        return 0.0


def build_albums(conn: sqlite3.Connection, gap_hours: float = GAP_HOURS, min_photos: int = MIN_PHOTOS) -> list[Album]:
    """Newest first.  Only photos with a capture date take part."""
    rows = conn.execute(
        "SELECT id, taken_at, place FROM items WHERE missing=0 AND kind='image' AND taken_at IS NOT NULL ORDER BY taken_at, id"
    ).fetchall()
    groups: list[list[sqlite3.Row]] = []
    for row in rows:
        if groups and _hours_between(groups[-1][-1]["taken_at"], row["taken_at"]) <= gap_hours:
            groups[-1].append(row)
        else:
            groups.append([row])
    albums: list[Album] = []
    for group in groups:
        if len(group) < min_photos:
            continue
        places: dict[str, int] = {}
        for r in group:
            if r["place"]:
                places[r["place"]] = places.get(r["place"], 0) + 1
        place = max(places, key=lambda k: places[k]).split(",")[0] if places else ""
        albums.append(
            Album(np.array([r["id"] for r in group], np.int64), group[0]["taken_at"][:10], group[-1]["taken_at"][:10], place)
        )
    return sorted(albums, key=lambda a: a.start, reverse=True)


def places_summary(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Every place with its photo count, most photos first."""
    rows = conn.execute(
        "SELECT place, COUNT(*) FROM items WHERE missing=0 AND place IS NOT NULL AND place<>'' GROUP BY place ORDER BY 2 DESC, 1"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]
