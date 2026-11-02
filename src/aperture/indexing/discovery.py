"""Find files on disk and keep the ``items`` table in sync with them.

All filesystem access here is read-only (``os.walk`` / ``os.stat``).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..config import Paths, preview_rel, thumb_rel
from ..search.textnorm import index_text

IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".bmp", ".gif"})
PDF_EXT = frozenset({".pdf"})
TEXT_EXT = frozenset({".txt", ".md"})
SKIP_DIRS = frozenset({"@eaDir", "node_modules", "$RECYCLE.BIN", "System Volume Information", ".Trashes", ".Spotlight-V100"})


@dataclass(frozen=True)
class FoundFile:
    path: str
    size: int
    mtime: float
    kind: str


@dataclass(frozen=True)
class ReconcileResult:
    found: int
    new: int
    changed: int
    missing: int


def classify(filename: str) -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in PDF_EXT:
        return "pdf"
    if ext in TEXT_EXT:
        return "text"
    return None


def discover(photo_dir: Path, skip: Path | None = None) -> list[FoundFile]:
    """Walk ``photo_dir``.  Hidden files are ignored - that includes the ``._*``
    AppleDouble stubs that exFAT/NTFS drives create next to every photo."""
    found: list[FoundFile] = []
    skip_str = str(skip) if skip else None
    for dirpath, dirnames, filenames in os.walk(photo_dir, followlinks=False):
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS and os.path.join(dirpath, d) != skip_str
        ]
        for name in filenames:
            if name.startswith("."):
                continue
            kind = classify(name)
            if kind is None:
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            found.append(FoundFile(full, st.st_size, st.st_mtime, kind))
    return found


def meta_text_for(rel_path: str, camera: str | None = None, lens: str | None = None) -> str:
    """Searchable text for the path engine."""
    return index_text(rel_path, camera or "", lens or "")


def delete_derived(conn: sqlite3.Connection, paths: Paths, item_ids: list[int]) -> None:
    """Remove thumbnails, previews, face crops, text and embeddings of items.

    Only Aperture's own derived files are touched - never originals."""
    for item_id in item_ids:
        for rel in (thumb_rel(item_id), preview_rel(item_id)):
            (paths.data / rel).unlink(missing_ok=True)
        conn.execute("DELETE FROM fts WHERE rowid=?", (item_id,))
        for (crop,) in conn.execute("SELECT crop FROM faces WHERE item_id=?", (item_id,)).fetchall():
            if crop:
                (paths.data / crop).unlink(missing_ok=True)
        conn.execute("DELETE FROM faces WHERE item_id=?", (item_id,))
        conn.execute("DELETE FROM embeddings WHERE item_id=?", (item_id,))


def reconcile(conn: sqlite3.Connection, paths: Paths, photo_dir: Path, files: list[FoundFile]) -> ReconcileResult:
    """Insert new files, reset changed ones, and flag vanished ones as missing."""
    existing = {r["path"]: r for r in conn.execute("SELECT id, path, size, mtime FROM items")}
    seen: set[str] = set()
    new = changed = 0
    for f in files:
        seen.add(f.path)
        rel = os.path.relpath(f.path, photo_dir)
        row = existing.get(f.path)
        clip_done = 1 if f.kind == "text" else 0
        faces_done = 0 if f.kind == "image" else 1
        if row is None:
            conn.execute(
                "INSERT INTO items(path, rel_path, meta_text, kind, size, mtime, clip_done, faces_done) VALUES (?,?,?,?,?,?,?,?)",
                (f.path, rel, meta_text_for(rel), f.kind, f.size, f.mtime, clip_done, faces_done),
            )
            new += 1
        elif row["size"] != f.size or abs((row["mtime"] or 0) - f.mtime) > 1:
            delete_derived(conn, paths, [row["id"]])
            conn.execute(
                "UPDATE items SET rel_path=?, meta_text=?, kind=?, size=?, mtime=?, meta_done=0, ocr_done=0, "
                "clip_done=?, faces_done=?, ocr_chars=0, error=NULL, notes=NULL, missing=0 WHERE id=?",
                (rel, meta_text_for(rel), f.kind, f.size, f.mtime, clip_done, faces_done, row["id"]),
            )
            changed += 1
        else:
            conn.execute("UPDATE items SET missing=0, rel_path=? WHERE id=?", (rel, row["id"]))
    gone = [r["id"] for p, r in existing.items() if p not in seen]
    # Never mark everything missing because a folder was empty or unmounted.
    if gone and files:
        conn.executemany("UPDATE items SET missing=1 WHERE id=?", [(i,) for i in gone])
    conn.commit()
    return ReconcileResult(found=len(files), new=new, changed=changed, missing=len(gone) if files else 0)


def purge_missing(conn: sqlite3.Connection, paths: Paths) -> int:
    """Drop index rows (and derived files) for originals that no longer exist."""
    ids = [r[0] for r in conn.execute("SELECT id FROM items WHERE missing=1")]
    if not ids:
        return 0
    delete_derived(conn, paths, ids)
    conn.executemany("DELETE FROM items WHERE id=?", [(i,) for i in ids])
    conn.execute(
        "DELETE FROM people WHERE name IS NULL AND id NOT IN (SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)"
    )
    conn.commit()
    return len(ids)
