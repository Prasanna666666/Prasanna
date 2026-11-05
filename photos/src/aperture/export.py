"""Safe export: copy photos into a folder on the external drive.

Guarantees
----------
* Originals are opened **read-only**; they are never moved, renamed or deleted.
* The destination must be on the external drive, outside the source folder and
  outside Aperture's own folder (see :func:`aperture.safety.resolve_export_dir`).
* Existing files are never overwritten.  Identical content is skipped
  (re-running an export is idempotent); different content gets a numbered name.
* Each copy is written to a ``.part`` file, SHA-256 verified (optional) and
  only then renamed into place, so a crash never leaves a half-written photo.
* A ``manifest.json`` records source, destination, size and checksum.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .config import Paths, Settings
from .db import chunked, in_clause
from .safety import SafetyError, WriteGuard, resolve_export_dir

CHUNK = 4 * 1024 * 1024
MIN_FREE_BYTES = 500 * 1024 * 1024
_UNSAFE = re.compile(r"[^\w\s().,&+-]", re.UNICODE)


@dataclass(frozen=True)
class ExportEntry:
    item_id: int
    source: str
    size: int


@dataclass
class ExportPlan:
    folder: Path
    entries: list[ExportEntry]
    unavailable: list[int] = field(default_factory=list)  # in the index but gone from disk
    total_bytes: int = 0
    free_bytes: int = 0

    @property
    def count(self) -> int:
        return len(self.entries)


@dataclass
class ExportReport:
    copied: int = 0
    skipped_identical: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    bytes_copied: int = 0
    folder: str = ""
    cancelled: bool = False


Progress = Callable[[int, int], None]


def sanitize_folder_name(name: str) -> str:
    """A single, safe folder name: no separators, no leading dots, bounded length."""
    base = _UNSAFE.sub("", name.replace("/", " ").replace("\\", " ")).strip().lstrip(".").strip()
    base = re.sub(r"\s+", " ", base)[:80]
    return base or f"Aperture export {datetime.now():%Y-%m-%d %H%M}"


def destination_for(paths: Paths, settings: Settings, folder_name: str) -> Path:
    """Where an export goes.  An absolute path is honoured (and validated);
    anything else becomes a sanitised subfolder of the configured export dir."""
    wanted = folder_name.strip()
    if wanted.startswith(("/", "~")):
        target = Path(wanted).expanduser()
    else:
        target = Path(settings.export_dir).expanduser() / sanitize_folder_name(wanted)
    return resolve_export_dir(paths, target, settings.photo_dir)


def build_plan(
    conn,
    paths: Paths,
    settings: Settings,
    item_ids: Sequence[int],
    folder_name: str,  # type: ignore[no-untyped-def]
) -> ExportPlan:
    """Validate the destination and collect what would be copied.  Copies nothing."""
    folder = destination_for(paths, settings, folder_name)
    ids = list(dict.fromkeys(int(i) for i in item_ids))  # de-duplicate, keep order
    found: dict[int, tuple[str, int]] = {}
    for part in chunked(ids):
        for row in conn.execute(f"SELECT id, path, size FROM items WHERE id IN ({in_clause(part)})", part):
            found[row["id"]] = (row["path"], row["size"])
    entries: list[ExportEntry] = []
    unavailable: list[int] = []
    for item_id in ids:
        path, size = found.get(item_id, ("", 0))
        if path and os.path.isfile(path):
            entries.append(ExportEntry(item_id, path, size or os.path.getsize(path)))
        else:
            unavailable.append(item_id)
    probe = folder
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return ExportPlan(
        folder=folder,
        entries=entries,
        unavailable=unavailable,
        total_bytes=sum(e.size for e in entries),
        free_bytes=shutil.disk_usage(probe).free,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_name(folder: Path, name: str) -> Path:
    stem, ext = os.path.splitext(name)
    candidate, n = folder / name, 1
    while candidate.exists():
        n += 1
        candidate = folder / f"{stem} ({n}){ext}"
    return candidate


def _copy_one(source: Path, folder: Path, guard: WriteGuard, verify: bool) -> tuple[Path | None, str, int]:
    """Copy one file.  Returns ``(destination or None if skipped, sha256, size)``."""
    size = source.stat().st_size
    digest = hashlib.sha256()
    target = folder / source.name
    if target.exists():
        if target.stat().st_size == size:
            with open(source, "rb") as handle:
                for block in iter(lambda: handle.read(CHUNK), b""):
                    digest.update(block)
            if digest.hexdigest() == _sha256(target):
                return None, digest.hexdigest(), size  # identical file already exported
        target = _unique_name(folder, source.name)
    guard.check(target)
    part = target.with_name(f".{target.name}.part")
    digest = hashlib.sha256()
    try:
        with open(source, "rb") as src, open(part, "wb") as dst:
            for block in iter(lambda: src.read(CHUNK), b""):
                digest.update(block)
                dst.write(block)
            dst.flush()
            os.fsync(dst.fileno())
        if part.stat().st_size != size:
            raise OSError("size mismatch after copy")
        if verify and _sha256(part) != digest.hexdigest():
            raise OSError("checksum mismatch after copy")
        shutil.copystat(source, part)  # keep the original timestamps on the copy
        os.replace(part, target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return target, digest.hexdigest(), size


def run_export(
    plan: ExportPlan,
    paths: Paths,
    settings: Settings,
    progress: Progress | None = None,
    stop: threading.Event | None = None,
) -> ExportReport:
    """Execute a plan.  Refuses to start without enough free space."""
    report = ExportReport(folder=str(plan.folder))
    needed = int(plan.total_bytes * 1.02) + MIN_FREE_BYTES
    if plan.free_bytes < needed:
        raise SafetyError(f"Not enough free space on the drive: need {needed / 1e9:.1f} GB, have {plan.free_bytes / 1e9:.1f} GB.")
    guard = WriteGuard(paths, export_root=plan.folder)
    guard.check(plan.folder)
    plan.folder.mkdir(parents=True, exist_ok=True)
    manifest_path = plan.folder / "manifest.json"
    manifest: list[dict[str, object]] = []
    try:
        manifest = json.loads(manifest_path.read_text()).get("files", [])
    except (OSError, ValueError, AttributeError):
        pass
    for index, entry in enumerate(plan.entries, start=1):
        if stop is not None and stop.is_set():
            report.cancelled = True
            break
        try:
            target, digest, size = _copy_one(Path(entry.source), plan.folder, guard, settings.export_verify)
        except (OSError, SafetyError) as exc:
            report.failed.append((entry.source, str(exc)))
        else:
            if target is None:
                report.skipped_identical += 1
            else:
                report.copied += 1
                report.bytes_copied += size
                manifest.append({"source": entry.source, "copy": str(target), "size": size, "sha256": digest})
        if progress is not None:
            progress(index, len(plan.entries))
    guard.check(manifest_path)
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"created": datetime.now().isoformat(timespec="seconds"), "files": manifest}, indent=1))
    os.replace(tmp, manifest_path)
    return report


# --------------------------------------------------------------------------
# Background jobs (run as `aperture export-job <id>` so the UI stays responsive)
# --------------------------------------------------------------------------
def create_job(paths: Paths, item_ids: Sequence[int], folder_name: str) -> str:
    paths.jobs.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "state": "queued", "folder_name": folder_name, "ids": [int(i) for i in item_ids],
           "done": 0, "total": len(item_ids), "created": time.time()}  # fmt: skip
    _write_job(paths, job_id, job)
    return job_id


def _write_job(paths: Paths, job_id: str, job: dict[str, object]) -> None:
    target = paths.jobs / f"{job_id}.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(job))
    os.replace(tmp, target)


def read_job(paths: Paths, job_id: str) -> dict[str, object] | None:
    try:
        data = json.loads((paths.jobs / f"{job_id}.json").read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def run_job(paths: Paths, settings: Settings, conn, job_id: str, stop: threading.Event | None = None) -> ExportReport:  # type: ignore[no-untyped-def]
    job = read_job(paths, job_id)
    if job is None:
        raise FileNotFoundError(f"unknown export job {job_id}")
    try:
        plan = build_plan(conn, paths, settings, job["ids"], str(job["folder_name"]))  # type: ignore[arg-type]
        job.update(state="running", total=plan.count, folder=str(plan.folder), unavailable=len(plan.unavailable))
        _write_job(paths, job_id, job)

        def on_progress(done: int, total: int) -> None:
            job.update(done=done, total=total)
            if done % 10 == 0 or done == total:
                _write_job(paths, job_id, job)

        report = run_export(plan, paths, settings, on_progress, stop)
        job.update(state="cancelled" if report.cancelled else "done", report=asdict(report), done=plan.count)
    except BaseException as exc:
        job.update(state="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        _write_job(paths, job_id, job)
    return report
