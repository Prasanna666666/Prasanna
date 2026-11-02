"""Duplicate detection and reversible file moves.

This is the **only** module that changes the library.  Guarantees:

* disabled unless the user switches ``allow_moves`` on;
* files are only ever *moved* (``os.rename`` on the same drive) - never deleted,
  overwritten, renamed in place or copied;
* both source and destination must be inside the photo folder, so the index
  stays valid (the scanner finds files at their new location);
* every move is journaled *before* it happens, so a crash can be audited
  and any batch can be undone.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .config import Paths, Settings
from .db import chunked, in_clause
from .indexing.discovery import meta_text_for
from .indexing.progress import ScanLock
from .models import Item
from .safety import SafetyError, is_inside

KEEP_RULES = {
    "oldest": "Keep the oldest photo",
    "newest": "Keep the newest photo",
    "largest": "Keep the largest file",
    "shortest_path": "Keep the one with the shortest path",
}
Progress = Callable[[int, int], None]


# --------------------------------------------------------------------------
# Duplicate detection (exact content match)
# --------------------------------------------------------------------------
def _sha256(path: str, stop: threading.Event | None = None) -> str | None:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:  # read-only
            while chunk := handle.read(1 << 20):
                if stop is not None and stop.is_set():
                    return None
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def find_exact_duplicates(
    conn: sqlite3.Connection,
    progress: Progress | None = None,
    stop: threading.Event | None = None,
) -> list[list[int]]:
    """Groups of item ids whose files are byte-identical (largest groups first).

    Only files that share a size are hashed, and hashes are cached in the
    database, so a repeat run is nearly instant and an interrupted run resumes."""
    sizes = conn.execute("SELECT size FROM items WHERE missing=0 AND size>0 GROUP BY size HAVING COUNT(*)>1").fetchall()
    candidates: list[tuple[int, str]] = []
    for part in chunked([r[0] for r in sizes]):
        candidates += [
            (r["id"], r["path"])
            for r in conn.execute(
                f"SELECT id, path FROM items WHERE missing=0 AND sha256 IS NULL AND size IN ({in_clause(part)})", part
            )
        ]
    for done, (item_id, path) in enumerate(candidates, start=1):
        if stop is not None and stop.is_set():
            break
        digest = _sha256(path, stop)
        if digest:
            conn.execute("UPDATE items SET sha256=? WHERE id=?", (digest, item_id))
        if done % 50 == 0:
            conn.commit()
        if progress:
            progress(done, len(candidates))
    conn.commit()
    groups: dict[str, list[int]] = defaultdict(list)
    for r in conn.execute("SELECT id, sha256 FROM items WHERE missing=0 AND sha256 IS NOT NULL ORDER BY id"):
        groups[r["sha256"]].append(r["id"])
    return sorted((g for g in groups.values() if len(g) > 1), key=lambda g: (-len(g), g[0]))


def choose_keeper(items: Sequence[Item], rule: str = "oldest") -> int:
    """Id of the copy to keep.  Ties fall back to the lowest id, so it is deterministic."""

    def date_key(i: Item) -> tuple[str, float, int]:
        return (i.taken_at or "9999", i.mtime, i.id)

    if rule == "newest":
        return max(items, key=lambda i: (i.taken_at or "", i.mtime, -i.id)).id
    if rule == "largest":
        return max(items, key=lambda i: (i.size, (i.width or 0) * (i.height or 0), -i.id)).id
    if rule == "shortest_path":
        return min(items, key=lambda i: (len(i.rel_path), i.id)).id
    return min(items, key=date_key).id


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MoveEntry:
    item_id: int
    src: str
    dst: str


@dataclass
class MovePlan:
    dest_dir: Path
    entries: list[MoveEntry] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (item id, reason)
    total_bytes: int = 0

    @property
    def count(self) -> int:
        return len(self.entries)


def move_problem(paths: Paths, settings: Settings) -> str | None:
    """Why moving is not possible right now (None = allowed)."""
    if not settings.allow_moves:
        return "Moving files is switched off. Turn it on first (originals stay untouched until you do)."
    if not settings.photo_dir:
        return "Choose the photo folder in Settings first."
    if ScanLock(paths).running():
        return "Indexing is running. Pause it before moving files."
    return None


def resolve_move_dir(paths: Paths, settings: Settings, candidate: str | Path) -> Path:
    """Destination must be inside the photo folder (so the index follows the files)."""
    photo = Path(settings.photo_dir).expanduser().resolve()
    target = Path(candidate).expanduser().resolve()
    if not is_inside(target, photo):
        raise SafetyError(f"Files can only be moved inside your photo folder ({photo}).")
    if target == photo:
        raise SafetyError("Choose a sub-folder, not the photo folder itself.")
    if is_inside(target, paths.root.resolve()):
        raise SafetyError("That folder is Aperture's own data folder.")
    return target


def default_move_dir(settings: Settings) -> str:
    return settings.move_dir or str(Path(settings.photo_dir) / "Aperture - moved duplicates")


def _free_name(taken: set[str], target: Path) -> Path:
    candidate, n = target, 1
    while str(candidate) in taken or candidate.exists():
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    taken.add(str(candidate))
    return candidate


def plan_move(
    conn: sqlite3.Connection,
    paths: Paths,
    settings: Settings,
    item_ids: Sequence[int],
    dest_dir: str | Path,
    keep_structure: bool = True,
) -> MovePlan:
    """Work out where each file would go.  Touches nothing on disk."""
    dest = resolve_move_dir(paths, settings, dest_dir)
    photo = Path(settings.photo_dir).expanduser().resolve()
    plan = MovePlan(dest_dir=dest)
    taken: set[str] = set()
    rows: dict[int, sqlite3.Row] = {}
    for part in chunked([int(i) for i in item_ids]):
        rows.update(
            {r["id"]: r for r in conn.execute(f"SELECT id, path, size, missing FROM items WHERE id IN ({in_clause(part)})", part)}
        )
    for item_id in item_ids:
        row = rows.get(int(item_id))
        if row is None or row["missing"]:
            plan.skipped.append((int(item_id), "no longer in the library"))
            continue
        src = Path(row["path"])
        if not src.is_file():
            plan.skipped.append((int(item_id), "file not found on disk"))
        elif is_inside(src.resolve(), dest):
            plan.skipped.append((int(item_id), "already in the destination folder"))
        elif not is_inside(src.resolve(), photo):
            plan.skipped.append((int(item_id), "outside the photo folder"))
        else:
            rel = src.resolve().relative_to(photo) if keep_structure else Path(src.name)
            plan.entries.append(MoveEntry(int(item_id), str(src), str(_free_name(taken, dest / rel))))
            plan.total_bytes += int(row["size"])
    return plan


def plan_duplicate_moves(
    conn: sqlite3.Connection,
    paths: Paths,
    settings: Settings,
    groups: Sequence[Sequence[int]],
    keepers: dict[int, int],
    dest_dir: str | Path,
) -> MovePlan:
    """Move every copy except the chosen keeper of each group (``keepers``: group index -> item id)."""
    to_move = [i for g, ids in enumerate(groups) for i in ids if i != keepers.get(g, ids[0])]
    return plan_move(conn, paths, settings, to_move, dest_dir)


# --------------------------------------------------------------------------
# Execution + undo
# --------------------------------------------------------------------------
@dataclass
class MoveReport:
    batch: str
    moved: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


def _repoint(conn: sqlite3.Connection, settings: Settings, item_id: int, new_path: str) -> None:
    rel = os.path.relpath(new_path, Path(settings.photo_dir).expanduser().resolve())
    row = conn.execute("SELECT camera, lens FROM items WHERE id=?", (item_id,)).fetchone()
    conn.execute(
        "UPDATE items SET path=?, rel_path=?, meta_text=? WHERE id=?",
        (new_path, rel, meta_text_for(rel, row["camera"] if row else None, row["lens"] if row else None), item_id),
    )


def _same_drive(a: Path, b: Path) -> bool:
    return os.stat(a).st_dev == os.stat(b).st_dev


def execute_move(
    conn: sqlite3.Connection,
    paths: Paths,
    settings: Settings,
    plan: MovePlan,
    label: str,
    progress: Progress | None = None,
) -> MoveReport:
    problem = move_problem(paths, settings)
    if problem:
        raise SafetyError(problem)
    batch = uuid.uuid4().hex[:12]
    conn.execute("INSERT INTO move_batches(id, label, created) VALUES (?,?,?)", (batch, label[:200], time.time()))
    report = MoveReport(batch=batch)
    photo = Path(settings.photo_dir).expanduser().resolve()
    for done, entry in enumerate(plan.entries, start=1):
        src, dst = Path(entry.src), Path(entry.dst)
        cur = conn.execute(
            "INSERT INTO moves(batch, item_id, src, dst, status) VALUES (?,?,?,?, 'pending')",
            (batch, entry.item_id, entry.src, entry.dst),
        )
        conn.commit()  # journal first, then act
        try:
            if not is_inside(src.resolve(), photo) or not is_inside(dst.resolve().parent, photo):
                raise SafetyError("outside the photo folder")
            if not src.is_file():
                raise FileNotFoundError("source file is gone")
            if dst.exists():
                raise FileExistsError("destination already exists")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not _same_drive(src.parent, dst.parent):
                raise SafetyError("destination is on a different volume")
            os.rename(src, dst)
            _repoint(conn, settings, entry.item_id, str(dst))
            conn.execute("UPDATE moves SET status='done' WHERE id=?", (cur.lastrowid,))
            report.moved += 1
        except (OSError, SafetyError) as exc:
            conn.execute("UPDATE moves SET status='failed', detail=? WHERE id=?", (str(exc), cur.lastrowid))
            report.failed.append((entry.src, str(exc)))
        conn.commit()
        if progress:
            progress(done, plan.count)
    return report


def undo_batch(conn: sqlite3.Connection, paths: Paths, settings: Settings, batch: str) -> MoveReport:
    """Put every file of a batch back where it was.  Never overwrites anything."""
    if ScanLock(paths).running():
        raise SafetyError("Indexing is running. Pause it before undoing.")
    report = MoveReport(batch=batch)
    photo = Path(settings.photo_dir).expanduser().resolve()
    rows = conn.execute(
        "SELECT id, item_id, src, dst FROM moves WHERE batch=? AND status='done' ORDER BY id DESC", (batch,)
    ).fetchall()
    for row in rows:
        src, dst = Path(row["src"]), Path(row["dst"])
        try:
            if not dst.is_file():
                raise FileNotFoundError("the moved file is no longer there")
            if src.exists():
                raise FileExistsError("something else is now at the original location")
            if not is_inside(src.resolve().parent, photo):
                raise SafetyError("original location is outside the photo folder")
            src.parent.mkdir(parents=True, exist_ok=True)
            os.rename(dst, src)
            _repoint(conn, settings, row["item_id"], str(src))
            conn.execute("UPDATE moves SET status='undone' WHERE id=?", (row["id"],))
            report.moved += 1
        except (OSError, SafetyError) as exc:
            conn.execute("UPDATE moves SET detail=? WHERE id=?", (f"undo failed: {exc}", row["id"]))
            report.failed.append((str(dst), str(exc)))
        conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM moves WHERE batch=? AND status='done'", (batch,)).fetchone()[0]
    if remaining == 0:
        conn.execute("UPDATE move_batches SET undone=1 WHERE id=?", (batch,))
        conn.commit()
    return report


@dataclass(frozen=True)
class BatchSummary:
    id: str
    label: str
    created: float
    moved: int
    undone: bool


def list_batches(conn: sqlite3.Connection, limit: int = 20) -> list[BatchSummary]:
    rows = conn.execute(
        "SELECT b.id, b.label, b.created, b.undone, "
        "(SELECT COUNT(*) FROM moves m WHERE m.batch=b.id AND m.status IN ('done','undone')) AS n "
        "FROM move_batches b ORDER BY b.created DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [BatchSummary(r["id"], r["label"], r["created"], r["n"], bool(r["undone"])) for r in rows]
