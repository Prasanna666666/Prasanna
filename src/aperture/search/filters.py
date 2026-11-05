"""Structured photo filters (time of day, weekday, orientation, people count, ...).

Every filter is plain, deterministic SQL.  The LLM only *fills in* a
:class:`Filters` value; it never decides which photos match.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, fields
from typing import Any

import numpy as np

from ..colors import color_clause, ensure_colors
from .geo import GeoIndex
from .metadata import remembered

TIMES_OF_DAY = ("none", "dawn", "morning", "afternoon", "evening", "night")
DAY_TYPES = ("none", "weekend", "weekday")
ORIENTATIONS = ("none", "landscape", "portrait", "square")
QUALITIES = ("none", "defects", "no_defects")
TRISTATE = ("none", "yes", "no")
KINDS = ("none", "image", "document")

# [from, to) in 24-hour local capture time; ranges may wrap past midnight
HOURS = {"dawn": (4, 7), "morning": (7, 12), "afternoon": (12, 17), "evening": (17, 21), "night": (21, 4)}
DEFAULT_RADIUS_KM = 25
FACE_MIN_SCORE, FACE_MIN_PX = 0.6, 40


@dataclass(frozen=True)
class Filters:
    time_of_day: str = "none"
    hour_from: int = -1  # explicit hours override time_of_day
    hour_to: int = -1
    day_type: str = "none"
    orientation: str = "none"
    min_people: int = -1
    max_people: int = -1
    quality: str = "none"
    has_gps: str = "none"
    kind: str = "none"
    near: str = ""
    radius_km: int = 0
    color: str = "none"

    @property
    def is_empty(self) -> bool:
        return self == Filters()

    def hours(self) -> tuple[int, int] | None:
        if 0 <= self.hour_from <= 23 and 0 <= self.hour_to <= 24:
            return self.hour_from, self.hour_to % 24
        return HOURS.get(self.time_of_day)

    def describe(self) -> str:
        parts: list[str] = []
        span = self.hours()
        if span:
            parts.append(
                self.time_of_day if self.time_of_day != "none" and self.hour_from < 0 else f"{span[0]:02d}:00-{span[1]:02d}:00"
            )
        for name in ("day_type", "orientation"):
            if getattr(self, name) != "none":
                parts.append(getattr(self, name))
        if self.min_people >= 0 or self.max_people >= 0:
            lo, hi = self.min_people, self.max_people
            parts.append(
                f"{lo}+ people"
                if hi < 0
                else (f"{lo} people" if lo == hi else (f"up to {hi} people" if lo <= 0 else f"{lo}-{hi} people"))
            )
        if self.quality != "none":
            parts.append("defect photos" if self.quality == "defects" else "not defect photos")
        if self.has_gps != "none":
            parts.append("with GPS" if self.has_gps == "yes" else "without GPS")
        if self.kind != "none":
            parts.append(self.kind + "s")
        if self.color != "none":
            parts.append(f"mostly {self.color}")
        if self.near:
            parts.append(f"within {self.radius_km or DEFAULT_RADIUS_KM} km of {self.near}")
        return ", ".join(parts)


def _ids(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> np.ndarray:
    return np.fromiter((r[0] for r in conn.execute(sql, params)), np.int64)


def haversine_km(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    p1, p2 = math.radians(lat), np.radians(lats)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lons - lon) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def apply_filters(conn: sqlite3.Connection, f: Filters, geo: GeoIndex | None) -> tuple[np.ndarray, list[str]]:
    """Ids of photos satisfying EVERY set filter, plus notes for the user."""
    notes: list[str] = []
    where: list[str] = ["missing=0", "meta_done=1"]
    params: list[Any] = []
    span = f.hours()
    if span:
        lo, hi = span
        hour = "CAST(substr(taken_at, 12, 2) AS INTEGER)"
        where.append("taken_exif=1")  # a file date has no meaningful time of day
        where.append(f"({hour} >= ? AND {hour} < ?)" if lo < hi else f"({hour} >= ? OR {hour} < ?)")
        params += [lo, hi]
        notes.append("Time of day only covers photos whose camera recorded the time.")
    if f.day_type != "none":
        where.append(
            "strftime('%w', substr(taken_at, 1, 10)) " + ("IN ('0','6')" if f.day_type == "weekend" else "NOT IN ('0','6')")
        )
    if f.orientation == "landscape":
        where.append("width > height * 1.05")
    elif f.orientation == "portrait":
        where.append("height > width * 1.05")
    elif f.orientation == "square":
        where.append("width BETWEEN height / 1.05 AND height * 1.05")
    if f.orientation != "none":
        where.append("width IS NOT NULL AND height IS NOT NULL")
    if f.quality == "defects":
        where.append("id IN (SELECT item_id FROM flags WHERE status='defect')")
    elif f.quality == "no_defects":
        where.append("id NOT IN (SELECT item_id FROM flags WHERE status='defect')")
    if f.color != "none":
        ensure_colors(conn)  # measured once per photo, from the small preview
        clause, color_params = color_clause(f.color)
        where.append(clause)
        params += color_params
        notes.append("Colour is the photo's overall dominant colour.")
    if f.has_gps != "none":
        where.append("gps_lat IS NOT NULL" if f.has_gps == "yes" else "gps_lat IS NULL")
    if f.kind == "image":
        where.append("kind='image'")
    elif f.kind == "document":
        where.append("kind IN ('pdf','text')")
    people = f"(SELECT COUNT(*) FROM faces fc WHERE fc.item_id=items.id AND fc.score>={FACE_MIN_SCORE} AND fc.px>={FACE_MIN_PX})"
    if f.min_people >= 0 or f.max_people >= 0:
        where.append("kind='image' AND faces_done=1")  # unknown until the face pass has looked at the photo
        if f.min_people > 0:
            where.append(f"{people} >= ?")
            params.append(f.min_people)
        if f.max_people >= 0:
            where.append(f"{people} <= ?")
            params.append(f.max_people)
        pending = remembered(
            conn,
            "faces_pending",
            lambda: conn.execute("SELECT COUNT(*) FROM items WHERE missing=0 AND kind='image' AND faces_done=0").fetchone()[0],
        )
        if pending:
            notes.append(f"Face detection has not finished for {pending:,} photos, so they cannot be counted yet.")
    sql = f"SELECT id FROM items WHERE {' AND '.join(where)}"
    ids = remembered(conn, ("filter", sql, tuple(params)), lambda: _ids(conn, sql, tuple(params)))

    if f.near:
        found = geo.find(f.near) if geo is not None else None
        if geo is None:
            notes.append("Place data is not installed (run `aperture fetch-models`), so I could not search near a place.")
            return np.zeros(0, np.int64), notes
        if found is None:
            notes.append(f"I do not know a place called '{f.near}'.")
            return np.zeros(0, np.int64), notes
        lat, lon, label = found
        rows = remembered(
            conn,
            "gps_positions",
            lambda: conn.execute(
                "SELECT id, gps_lat, gps_lon FROM items WHERE missing=0 AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL"
            ).fetchall(),
        )
        if rows:
            near = np.array([r["id"] for r in rows], np.int64)
            dist = haversine_km(lat, lon, np.array([r["gps_lat"] for r in rows]), np.array([r["gps_lon"] for r in rows]))
            ids = np.intersect1d(ids, near[dist <= (f.radius_km or DEFAULT_RADIUS_KM)])
        else:
            ids = np.zeros(0, np.int64)
        notes.append(f"'{f.near}' matched {label}.")
    return ids, notes


FILTER_FIELDS = tuple(x.name for x in fields(Filters))
