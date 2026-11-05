"""Orchestrates a full, resumable scan: discover -> index -> faces -> OCR."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import Paths, Settings
from ..db import Database, meta_get, meta_set
from ..people.clustering import cluster_faces
from ..safety import WriteGuard, resolve_photo_dir
from .discovery import discover, purge_missing, reconcile
from .pipeline import (
    STAGE_FACES,
    STAGE_INDEX,
    STAGE_OCR,
    Job,
    ResultWriter,
    Services,
    WorkResult,
    process_job,
)
from .progress import ProgressReporter, ScanLock

log = logging.getLogger(__name__)

ServicesFactory = Callable[[str], Services]


@dataclass
class ScanOptions:
    retry_errors: bool = False
    limit: int = 0  # 0 = no limit (testing aid only)
    regroup_faces: bool = False


@dataclass
class ScanSummary:
    state: str = "done"
    processed: int = 0
    errors: int = 0
    faces: int = 0
    purged: int = 0


_TODO_SQL = {
    STAGE_INDEX: (
        "SELECT id, path, kind, mtime, meta_done, clip_done FROM items WHERE missing=0 "
        "AND (error IS NULL OR :retry) AND (meta_done=0 OR (:clip AND clip_done=0 AND kind IN ('image','pdf'))) "
        "ORDER BY id"
    ),
    STAGE_FACES: (
        "SELECT id, path, kind, mtime, meta_done, clip_done FROM items WHERE missing=0 AND error IS NULL "
        "AND meta_done=1 AND faces_done=0 AND kind='image' ORDER BY id"
    ),
    STAGE_OCR: (
        "SELECT id, path, kind, mtime, meta_done, clip_done FROM items WHERE missing=0 AND error IS NULL "
        "AND ocr_done=0 AND (:images OR kind IN ('pdf','text')) ORDER BY id"
    ),
}


def _params_for(stage: str, values: dict[str, int]) -> dict[str, int]:
    if stage == STAGE_INDEX:
        return {"retry": values["retry"], "clip": values["clip"]}
    if stage == STAGE_OCR:
        return {"images": values["images"]}
    return {}


class Scanner:
    def __init__(
        self,
        paths: Paths,
        settings: Settings,
        db: Database,
        services_factory: ServicesFactory,
        stop: threading.Event | None = None,
    ) -> None:
        self.paths, self.settings, self.db = paths, settings, db
        self._factory = services_factory
        self._stop = stop or threading.Event()
        self.guard = WriteGuard(paths)

    def _skipped(self) -> list[Path]:
        """Folders never scanned: Aperture's own data and the export folder (copies, not originals)."""
        skip = [self.paths.root]
        if self.settings.export_dir:
            skip.append(Path(self.settings.export_dir).expanduser())
        return skip

    # ------------------------------------------------------------------
    def run(self, options: ScanOptions | None = None) -> ScanSummary:
        opts = options or ScanOptions()
        lock, progress = ScanLock(self.paths), ProgressReporter(self.paths)
        if not lock.acquire():
            log.info("A scan is already running.")
            return ScanSummary(state="busy")
        summary = ScanSummary()
        try:
            progress.update(force=True, state="starting", message="Looking for files...")
            photo_dir = resolve_photo_dir(self.paths, self.settings.photo_dir)
            if not photo_dir.is_dir():
                raise FileNotFoundError(f"Photo folder not found: {photo_dir}")
            conn = self.db.connect()
            self._check_embedding_model(conn)
            found = reconcile(conn, self.paths, photo_dir, discover(photo_dir, skip=self._skipped()))
            log.info("found %d files (%d new, %d changed)", found.found, found.new, found.changed)

            stages = self.settings.stages
            plan = [(STAGE_INDEX, True), (STAGE_FACES, stages.faces), (STAGE_OCR, stages.ocr)]
            for stage, enabled in plan:
                if enabled and not self._stop.is_set():
                    self._run_pass(conn, stage, opts, progress, summary)
            if summary.faces or opts.regroup_faces:
                progress.update(force=True, stage="people", message="Grouping faces...")
                s = self.settings
                cluster_faces(conn, threshold=s.cluster_threshold, min_score=s.face_min_score, min_px=s.face_min_px)
            if found.found:
                summary.purged = purge_missing(conn, self.paths)
            meta_set(conn, "embed_version", str(time.time()))
            meta_set(conn, "last_scan", datetime.now().isoformat(timespec="seconds"))
            conn.commit()
            summary.state = "stopped" if self._stop.is_set() else "done"
            progress.update(
                force=True, state=summary.state, stage="", current="",
                message=f"{summary.processed} processed, {summary.errors} errors, {summary.faces} faces",
            )  # fmt: skip
        except BaseException as exc:
            progress.update(force=True, state="error", message=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            lock.release()
        return summary

    # ------------------------------------------------------------------
    def _check_embedding_model(self, conn) -> None:  # type: ignore[no-untyped-def]
        """Embeddings from a different CLIP model are meaningless: redo them."""
        wanted = f"{self.settings.clip_model}/{self.settings.clip_pretrained}"
        current = meta_get(conn, "clip_model")
        if current not in (None, wanted):
            conn.execute("DELETE FROM embeddings")
            conn.execute("UPDATE items SET clip_done=0 WHERE kind IN ('image','pdf')")
            conn.execute(
                "DELETE FROM photo_labels WHERE source IN ('clip', 'face')"
            )  # everything derived from the old model's vectors
            conn.execute("DELETE FROM face_attributes")
        meta_set(conn, "clip_model", wanted)
        conn.commit()

    def _run_pass(self, conn, stage: str, opts: ScanOptions, progress: ProgressReporter, summary: ScanSummary) -> None:  # type: ignore[no-untyped-def]
        precheck = {"retry": int(opts.retry_errors), "clip": int(self.settings.stages.clip), "images": 1}
        if not conn.execute(_TODO_SQL[stage], _params_for(stage, precheck)).fetchall():
            return  # nothing to do: do not spend half a minute loading models for it
        svc = self._factory(stage)
        want_clip = self.settings.stages.clip and svc.embedder is not None
        params: dict[str, int] = {}
        if stage == STAGE_INDEX:
            params = {"retry": int(opts.retry_errors), "clip": int(want_clip)}
        elif stage == STAGE_OCR:
            params = {"images": int(svc.ocr is not None)}
        rows = conn.execute(_TODO_SQL[stage], params).fetchall()
        if stage == STAGE_FACES and svc.faces is None:
            rows = []
        if opts.limit:
            rows = rows[: opts.limit]
        jobs = [
            Job(r["id"], r["path"], r["kind"], r["mtime"], stage,
                need_meta=not r["meta_done"], need_clip=want_clip and not r["clip_done"])
            for r in rows
        ]  # fmt: skip
        progress.update(force=True, state="running", stage=stage, total=len(jobs), done=0, errors=0)
        writer = ResultWriter(conn, self.paths, self.guard, svc.embedder, self.settings.batch_size)
        started, done, errors = time.time(), 0, 0
        try:
            for result in self._execute(jobs, svc):
                writer.apply(result)
                done += 1
                errors += 1 if result.error else 0
                rate = done / max(time.time() - started, 1e-6)
                progress.update(
                    done=done, errors=errors, current=result.job.path.rsplit("/", 1)[-1],
                    message=f"{rate:.1f} files/s", eta=(len(jobs) - done) / rate if rate else None,
                )  # fmt: skip
                if done % 25 == 0:
                    conn.commit()
            writer.finish()
        finally:
            if svc.embedder is not None:
                svc.embedder.close()  # give the GPU memory back before the next pass
        summary.processed += done
        summary.errors += errors
        summary.faces += writer.faces_added

    def _execute(self, jobs: list[Job], svc: Services):  # type: ignore[no-untyped-def]
        """Run jobs on a bounded thread pool, yielding results as they finish."""
        s = self.settings
        window = max(4, s.workers * 3)
        pending = iter(jobs)
        inflight: set[Future[WorkResult]] = set()
        with ThreadPoolExecutor(max_workers=s.workers) as pool:

            def fill() -> None:
                while len(inflight) < window and not self._stop.is_set():
                    job = next(pending, None)
                    if job is None:
                        return
                    inflight.add(pool.submit(process_job, job, svc, s, self.paths, self.guard))

            fill()
            while inflight:
                finished, _ = wait(inflight, timeout=1.0, return_when=FIRST_COMPLETED)
                for future in finished:
                    inflight.discard(future)
                    yield future.result()
                fill()
