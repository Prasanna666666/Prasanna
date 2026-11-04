"""Age of every face in years (InsightFace age model), turned into searchable labels only where the estimate is clearly inside a group.

Reads the saved face crops, never the original photo. A label from this model is a second, independent source next to the image-search
model's guess, so a photo is trusted as a "baby" photo when both agree, or when this one is clear on its own.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..ml.age import age_group

LABEL_SCORE = 0.85  # an estimate that sits well inside a group counts as strong


def pending(conn: sqlite3.Connection, limit: int = 0) -> list[tuple[int, int, str]]:
    sql = ("SELECT f.id, f.item_id, f.crop FROM faces f LEFT JOIN face_ages a ON a.face_id=f.id "
           "WHERE a.face_id IS NULL AND f.crop IS NOT NULL ORDER BY f.id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [(r[0], r[1], r[2]) for r in conn.execute(sql)]


def run(conn: sqlite3.Connection, data_dir: Path, estimator: Any, limit: int = 0, stop: Any = None) -> int:
    from PIL import Image

    done = 0
    for n, (face_id, _item, crop) in enumerate(pending(conn, limit), 1):
        if stop is not None and stop.is_set():
            break
        try:
            with Image.open(data_dir / crop) as image:
                years = estimator.estimate(image)
        except Exception:
            continue
        conn.execute("INSERT OR REPLACE INTO face_ages(face_id, years) VALUES (?,?)", (face_id, years))
        done += 1
        if n % 500 == 0:
            conn.commit()
    conn.commit()
    return done


def make_labels(conn: sqlite3.Connection) -> int:
    """Searchable labels (source 'age') from the stored estimates: one per photo and group, only for estimates clearly inside a group."""
    conn.execute("DELETE FROM photo_labels WHERE source='age'")
    seen: set[tuple[int, str]] = set()
    for item_id, years in conn.execute("SELECT f.item_id, a.years FROM face_ages a JOIN faces f ON f.id=a.face_id"):
        group = age_group(years)
        if group:
            seen.add((item_id, group))
    conn.executemany("INSERT INTO photo_labels(item_id, label, score, source) VALUES (?,?,?,'age')", [(i, g, LABEL_SCORE) for i, g in seen])
    conn.commit()
    return len(seen)
