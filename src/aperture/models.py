"""Typed value objects shared across layers.

``Item.from_row`` never raises on missing columns or ``None`` rows, which is
what keeps the UI from crashing on a half-indexed or older database.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import PurePath
from typing import Any

KINDS = ("image", "pdf", "text")


@dataclass(slots=True)
class Item:
    id: int = 0
    path: str = ""
    rel_path: str = ""
    kind: str = "image"
    size: int = 0
    mtime: float = 0.0
    width: int | None = None
    height: int | None = None
    taken_at: str | None = None
    camera: str | None = None
    lens: str | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    place: str | None = None
    thumb: str | None = None
    preview: str | None = None
    error: str | None = None
    notes: str | None = None
    missing: int = 0
    sharp: float | None = None
    bright: float | None = None
    contrast: float | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | Any | None) -> Item:
        """Build an Item from a ``sqlite3.Row`` / dict, tolerating gaps."""
        if row is None:
            return cls()
        try:
            keys = set(row.keys())
        except AttributeError:
            return cls()
        values: dict[str, Any] = {}
        for f in fields(cls):
            if f.name in keys and row[f.name] is not None:
                values[f.name] = row[f.name]
        return cls(**values)

    @property
    def name(self) -> str:
        return PurePath(self.path).name or f"item {self.id}"

    @property
    def year(self) -> int | None:
        try:
            return int((self.taken_at or "")[:4])
        except ValueError:
            return None

    @property
    def date_label(self) -> str:
        return (self.taken_at or "")[:10] or "undated"

    @property
    def caption(self) -> str:
        """Human-readable one-liner used as image caption / accessible name."""
        parts = [self.name, self.date_label]
        if self.place:
            parts.append(self.place)
        return " - ".join(parts)
