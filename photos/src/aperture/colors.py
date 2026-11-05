"""Dominant colour of each photo, measured from its small preview (cheap, offline)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image

COLORS = ("none", "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink", "brown", "black", "white", "gray")
# hue ranges in degrees for saturated colours; neutrals and brown are decided by saturation and brightness
_HUES = {
    "orange": (15, 45), "yellow": (45, 70), "green": (70, 165), "teal": (165, 200),
    "blue": (200, 255), "purple": (255, 290), "pink": (290, 345),
}  # fmt: skip
MIN_SAT = 0.22


def measure(image: Image.Image) -> tuple[float, float, float]:
    """(hue 0-360, saturation 0-1, value 0-1): the average colour, weighting vivid pixels more for the hue."""
    rgb = np.asarray(image.convert("RGB").resize((24, 24)), dtype=np.float32).reshape(-1, 3) / 255.0
    top, low = rgb.max(axis=1), rgb.min(axis=1)
    delta = top - low
    sat = np.where(top > 0, delta / np.maximum(top, 1e-9), 0.0)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    hue = np.zeros(len(rgb), np.float32)
    mask = delta > 0
    rm, gm, bm = mask & (top == r), mask & (top == g) & (top != r), mask & (top == b) & (top != r) & (top != g)
    hue[rm] = ((g - b)[rm] / delta[rm]) % 6
    hue[gm] = (b - r)[gm] / delta[gm] + 2
    hue[bm] = (r - g)[bm] / delta[bm] + 4
    angle = hue / 6 * 2 * np.pi
    x, y = float((np.cos(angle) * sat).sum()), float((np.sin(angle) * sat).sum())
    mean_hue = float(np.degrees(np.arctan2(y, x)) % 360) if (x or y) else 0.0
    return mean_hue, float(sat.mean()), float(top.mean())


def data_dir(conn: sqlite3.Connection) -> Path:
    row = conn.execute("PRAGMA database_list").fetchone()
    return Path(row[2]).parent


def ensure_colors(conn: sqlite3.Connection) -> int:
    """Measure every photo that has a preview but no colour yet; returns how many were measured."""
    root = data_dir(conn)
    rows = conn.execute(
        "SELECT id, thumb FROM items WHERE missing=0 AND kind='image' AND hue IS NULL AND thumb IS NOT NULL"
    ).fetchall()
    done = 0
    for row in rows:
        try:
            with Image.open(root / row["thumb"]) as image:
                h, s, v = measure(image)
        except (OSError, ValueError):
            h, s, v = -1.0, 0.0, 0.0  # unreadable preview: mark as measured so we do not retry forever
        conn.execute("UPDATE items SET hue=?, sat=?, val=? WHERE id=?", (h, s, v, row["id"]))
        done += 1
        if done % 200 == 0:
            conn.commit()
    conn.commit()
    return done


def color_clause(name: str) -> tuple[str, list[float]]:
    """SQL condition (and parameters) selecting photos whose dominant colour is ``name``."""
    if name == "black":
        return "(hue>=0 AND val < 0.2)", []
    if name == "white":
        return "(hue>=0 AND val > 0.8 AND sat < 0.15)", []
    if name == "gray":
        return "(hue>=0 AND sat < 0.12 AND val >= 0.2 AND val <= 0.8)", []
    if name == "brown":
        return "(hue>=15 AND hue<45 AND sat>=0.3 AND val<0.55 AND val>=0.15)", []
    if name == "red":
        return "(hue>=0 AND sat>=? AND (hue>=345 OR hue<15))", [MIN_SAT]
    if name in _HUES:
        lo, hi = _HUES[name]
        extra = " AND val>=0.55" if name == "orange" else ""
        return f"(hue>=? AND hue<? AND sat>=?{extra})", [lo, hi, MIN_SAT]
    return "1=1", []
