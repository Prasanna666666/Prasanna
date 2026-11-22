"""Storage usage and disk pressure (Stage 4; UC-044). Reports what the Core's own data uses, by category, and what the Core may do about pressure.

The rule that matters: pressure can PAUSE derived work (cache rebuilds, index growth, new backups) and tell the owner; it can never delete an original, a task, a grant or a backup, and nothing is dropped
silently. Derived data (the indexes) is the only thing the owner may ask to have rebuilt, and that is an explicit action, not a pressure response.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

GIB = 1 << 30
LOW_FREE_FRACTION, CRITICAL_FREE_FRACTION = 0.10, 0.03
LOW_FREE_BYTES, CRITICAL_FREE_BYTES = 10 * GIB, 2 * GIB

CATEGORIES = {
    "tasks": ("tasks.db", "tasks.db-wal", "tasks.db-shm"),
    "designation": ("designation.db", "designation.db-wal", "designation.db-shm", "clients.json", "core.lock"),
    "indexes": ("documents.db", "documents.db-wal", "documents.db-shm", "mail.db", "mail.db-wal", "mail.db-shm"),
}
# what pressure may do, by level; every entry pauses or warns, none deletes
ACTIONS = {
    "ok": (),
    "low": ("tell_owner", "pause_cache_rebuilds", "defer_new_backups_to_other_volume"),
    "critical": ("tell_owner", "pause_cache_rebuilds", "pause_index_growth", "refuse_new_backups_here"),
}
NEVER = ("delete_original", "delete_task", "delete_grant", "delete_backup")


@dataclass(frozen=True)
class StorageReport:
    bytes_by_category: dict[str, int]
    free_bytes: int
    total_bytes: int
    pressure: str  # ok | low | critical
    actions: tuple[str, ...]
    budget_bytes: int | None
    over_budget: bool


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


def pressure_of(free: int, total: int) -> str:
    """`critical` below 3% free or 2 GiB; `low` below 10% free or 10 GiB; otherwise `ok`. Either the fraction or the absolute floor trips it, whichever is stricter."""
    if free < max(total * CRITICAL_FREE_FRACTION, CRITICAL_FREE_BYTES):
        return "critical"
    if free < max(total * LOW_FREE_FRACTION, LOW_FREE_BYTES):
        return "low"
    return "ok"


def report(
    data_dir: Path, *, backups_dir: Path | None = None, budget_bytes: int | None = None, usage: Callable[[Path], tuple[int, int, int]] = shutil.disk_usage
) -> StorageReport:
    """What the Core's data uses, where. Originals are never copied into the data folder, so they are not counted: the report says what Atlas itself holds."""
    counted: dict[str, int] = {name: sum(_size(data_dir / f) for f in files) for name, files in CATEGORIES.items()}
    known = {f for files in CATEGORIES.values() for f in files} | {"models", "history"}
    counted["models"] = _size(data_dir / "models")
    counted["history"] = _size(data_dir / "history")
    counted["other"] = sum(_size(p) for p in data_dir.iterdir() if p.name not in known) if data_dir.exists() else 0
    if backups_dir is not None:
        counted["backups"] = _size(backups_dir)
    total, _used, free = usage(data_dir if data_dir.exists() else data_dir.parent)
    level = pressure_of(free, total)
    held = sum(counted.values())
    return StorageReport(counted, free, total, level, ACTIONS[level], budget_bytes, budget_bytes is not None and held > budget_bytes)
