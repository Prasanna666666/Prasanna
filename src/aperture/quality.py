"""Photo quality: sharpness/exposure metrics, defect suggestions and labels.

Metrics are measured on Aperture's own previews (never on the originals) at a
fixed 512 px size, so values are comparable between photos.  Suggestions are
only that: nothing is labelled until the user confirms, and labels live in the
database - no file is touched.
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .config import Paths, preview_rel
from .db import chunked, in_clause

ANALYSIS_SIDE = 512
BLOCK = 32
Progress = Callable[[int, int], None]

# sensitivity -> (blur below, too dark below, too bright above)
SENSITIVITY: dict[str, tuple[float, float, float]] = {
    "low": (10.0, 25.0, 235.0),
    "medium": (25.0, 40.0, 220.0),
    "high": (50.0, 55.0, 205.0),
}
BLANK_CONTRAST = 6.0


@dataclass(frozen=True)
class Metrics:
    sharp: float
    bright: float
    contrast: float


def analyze_gray(gray: np.ndarray) -> Metrics:
    """Metrics of a 2-D float array (luminance 0-255)."""
    g = gray.astype(np.float32)
    if min(g.shape) < 3:
        return Metrics(0.0, float(g.mean()), float(g.std()))
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    hb, wb = lap.shape[0] // BLOCK, lap.shape[1] // BLOCK
    if hb and wb:
        blocks = lap[: hb * BLOCK, : wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).var(axis=(1, 3))
        # The 95th percentile block: a sharp subject on a soft background still counts as sharp.
        sharp = float(np.percentile(blocks, 95))
    else:
        sharp = float(lap.var())
    return Metrics(sharp, float(g.mean()), float(g.std()))


def analyze_file(path: Path) -> Metrics | None:
    try:
        with Image.open(path) as img:
            img = img.convert("L")
            img.thumbnail((ANALYSIS_SIDE, ANALYSIS_SIDE), Image.Resampling.LANCZOS)
            return analyze_gray(np.asarray(img))
    except (OSError, ValueError):
        return None


def ensure_quality(
    conn: sqlite3.Connection,
    paths: Paths,
    ids: Iterable[int] | None = None,
    progress: Progress | None = None,
    stop: threading.Event | None = None,
) -> int:
    """Measure every image that has a preview and no metrics yet.  Resumable."""
    todo: list[int] = []
    if ids is None:
        todo = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM items WHERE missing=0 AND kind='image' AND preview IS NOT NULL AND sharp IS NULL"
            )
        ]
    else:
        for part in chunked([int(i) for i in ids]):
            todo += [
                r[0]
                for r in conn.execute(
                    f"SELECT id FROM items WHERE missing=0 AND kind='image' AND preview IS NOT NULL AND sharp IS NULL AND id IN ({in_clause(part)})",
                    part,
                )
            ]
    done = 0
    for n, item_id in enumerate(todo, start=1):
        if stop is not None and stop.is_set():
            break
        m = analyze_file(paths.data / preview_rel(item_id))
        if m:
            conn.execute("UPDATE items SET sharp=?, bright=?, contrast=? WHERE id=?", (m.sharp, m.bright, m.contrast, item_id))
            done += 1
        if n % 200 == 0:
            conn.commit()
        if progress:
            progress(n, len(todo))
    conn.commit()
    return done


def quality_score(m: Metrics, pixels: int = 0) -> float:
    """Higher is better: sharpness first, then exposure, then resolution."""
    exposure_penalty = min(1.0, abs(m.bright - 125.0) / 125.0)
    return math.log1p(m.sharp) - exposure_penalty + 0.05 * math.log10(max(pixels, 1))


def best_of(conn: sqlite3.Connection, ids: Sequence[int]) -> int:
    """The best-looking photo of a group (lowest id wins ties; unmeasured photos rank last)."""
    rows = {
        r["id"]: r
        for part in chunked([int(i) for i in ids])
        for r in conn.execute(
            f"SELECT id, sharp, bright, contrast, width, height FROM items WHERE id IN ({in_clause(part)})", part
        )
    }

    def key(i: int) -> tuple[float, int]:
        r = rows.get(i)
        if r is None or r["sharp"] is None:
            return (-1e9, -i)
        return (quality_score(Metrics(r["sharp"], r["bright"], r["contrast"]), (r["width"] or 0) * (r["height"] or 0)), -i)

    return max(ids, key=key)


# --------------------------------------------------------------------------
# Defect suggestions and labels
# --------------------------------------------------------------------------
def defect_reason(m: Metrics, sensitivity: str = "medium") -> str | None:
    blur, dark, bright = SENSITIVITY.get(sensitivity, SENSITIVITY["medium"])
    if m.contrast < BLANK_CONTRAST:
        return "blank or covered lens"
    if m.bright < dark:
        return "too dark"
    if m.bright > bright:
        return "too bright"
    if m.sharp < blur:
        return "blurry"
    return None


def suggest_defects(conn: sqlite3.Connection, sensitivity: str = "medium") -> list[tuple[int, str]]:
    """Measured photos that look defective and that the user has not reviewed yet."""
    out: list[tuple[int, str]] = []
    rows = conn.execute(
        "SELECT id, sharp, bright, contrast FROM items WHERE missing=0 AND sharp IS NOT NULL "
        "AND id NOT IN (SELECT item_id FROM flags) ORDER BY taken_at DESC, id"
    )
    for r in rows:
        reason = defect_reason(Metrics(r["sharp"], r["bright"], r["contrast"]), sensitivity)
        if reason:
            out.append((r["id"], reason))
    return out


def set_defects(conn: sqlite3.Connection, marks: Iterable[tuple[int, str]]) -> int:
    rows = [(int(i), reason, time.time()) for i, reason in marks]
    conn.executemany(
        "INSERT INTO flags(item_id, status, reason, created) VALUES (?, 'defect', ?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET status='defect', reason=excluded.reason, created=excluded.created",
        [(i, r, t) for i, r, t in rows],
    )
    conn.commit()
    return len(rows)


def mark_ok(conn: sqlite3.Connection, ids: Iterable[int]) -> int:
    rows = [(int(i), time.time()) for i in ids]
    conn.executemany(
        "INSERT INTO flags(item_id, status, reason, created) VALUES (?, 'ok', '', ?) "
        "ON CONFLICT(item_id) DO UPDATE SET status='ok', reason='', created=excluded.created",
        rows,
    )
    conn.commit()
    return len(rows)


def unmark(conn: sqlite3.Connection, ids: Iterable[int]) -> None:
    conn.executemany("DELETE FROM flags WHERE item_id=?", [(int(i),) for i in ids])
    conn.commit()


def defect_ids(conn: sqlite3.Connection) -> np.ndarray:
    rows = conn.execute(
        "SELECT f.item_id FROM flags f JOIN items i ON i.id=f.item_id WHERE f.status='defect' AND i.missing=0 ORDER BY i.taken_at DESC, i.id"
    )
    return np.fromiter((r[0] for r in rows), np.int64)


def defect_reasons(conn: sqlite3.Connection, ids: Sequence[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for part in chunked([int(i) for i in ids]):
        out.update(
            {
                r["item_id"]: r["reason"] or "defect"
                for r in conn.execute(
                    f"SELECT item_id, reason FROM flags WHERE status='defect' AND item_id IN ({in_clause(part)})", part
                )
            }
        )
    return out
