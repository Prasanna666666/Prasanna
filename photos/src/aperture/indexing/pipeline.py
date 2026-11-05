"""The three indexing passes.

``process_job`` is the heavy, thread-safe half (decode, OCR, face analysis).
``ResultWriter`` is the single-threaded half that owns the SQLite connection.
Splitting them keeps the database free of locking problems and makes each half
easy to test in isolation.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..config import Paths, Settings, face_rel, preview_rel, thumb_rel
from ..db import meta_set
from ..ml.protocols import DetectedFace, FaceAnalyzer, ImageEmbedder, TextRecognizer
from ..safety import WriteGuard
from ..search.geo import GeoIndex
from . import loaders
from .discovery import meta_text_for

STAGE_INDEX, STAGE_FACES, STAGE_OCR = "index", "faces", "ocr"


@dataclass
class Services:
    """ML dependencies injected into the pipeline (all optional)."""

    embedder: ImageEmbedder | None = None
    faces: FaceAnalyzer | None = None
    ocr: TextRecognizer | None = None
    geo: GeoIndex | None = None


@dataclass
class Job:
    id: int
    path: str
    kind: str
    mtime: float
    stage: str
    need_meta: bool = False
    need_clip: bool = False


@dataclass
class WorkResult:
    job: Job
    meta: loaders.FileMeta | None = None
    place: tuple[str, str] | None = None  # (label, folded search text)
    text: str | None = None
    tensor: Any = None
    faces: list[DetectedFace] | None = None
    face_image: Any = None
    error: str | None = None
    note: str | None = None
    taken_exif: bool = False


# --------------------------------------------------------------------------
# Worker half (thread-safe, never touches SQLite)
# --------------------------------------------------------------------------
def process_job(job: Job, svc: Services, settings: Settings, paths: Paths, guard: WriteGuard) -> WorkResult:
    result = WorkResult(job=job)
    try:
        if job.stage == STAGE_INDEX:
            _index(job, svc, settings, paths, guard, result)
        elif job.stage == STAGE_FACES:
            _faces(job, svc, paths, result)
        elif job.stage == STAGE_OCR:
            _ocr(job, svc, settings, result)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def _index(job: Job, svc: Services, st: Settings, paths: Paths, guard: WriteGuard, out: WorkResult) -> None:
    if job.kind == "image":
        image, meta = loaders.load_image(job.path, st.preview_size)
    elif job.kind == "pdf":
        image, meta, _ = loaders.load_pdf(job.path, recognizer=None, max_pages=1, want_text=False)
    else:
        meta = loaders.FileMeta()
        image = loaders.make_text_thumb(Path(job.path).name, loaders.read_text_file(job.path), st.thumb_size)
    preview = image.copy()
    preview.thumbnail((st.preview_size, st.preview_size))
    if job.need_meta:
        thumb = preview.copy()
        thumb.thumbnail((st.thumb_size, st.thumb_size))
        loaders.save_jpeg(guard, thumb, paths.data / thumb_rel(job.id), 82)
        loaders.save_jpeg(guard, preview, paths.data / preview_rel(job.id), 85)
        out.taken_exif = meta.taken_at is not None
        meta.taken_at = meta.taken_at or loaders.file_date(job.mtime)
        out.meta = meta
        if svc.geo is not None and meta.gps_lat is not None and meta.gps_lon is not None:
            place = svc.geo.lookup(meta.gps_lat, meta.gps_lon)
            if place is not None:
                out.place = (place.label, place.search_text)
    if job.need_clip and svc.embedder is not None and job.kind in ("image", "pdf"):
        out.tensor = svc.embedder.preprocess(preview)


def _faces(job: Job, svc: Services, paths: Paths, out: WorkResult) -> None:
    """Face analysis reads the small preview JPEG - the original is not touched again."""
    if svc.faces is None:
        return
    image = loaders.load_preview(paths.data / preview_rel(job.id))
    bgr = np.ascontiguousarray(np.asarray(image)[:, :, ::-1])
    out.faces = svc.faces.analyse(bgr)
    out.face_image = image


def _ocr(job: Job, svc: Services, st: Settings, out: WorkResult) -> None:
    if job.kind == "text":
        out.text = loaders.read_text_file(job.path)
    elif job.kind == "pdf":
        _, _, out.text = loaders.load_pdf(job.path, recognizer=svc.ocr, max_pages=st.ocr_max_pdf_pages, want_text=True)
    elif svc.ocr is not None:
        image, _ = loaders.load_image(job.path, st.ocr_max_side)
        if min(image.size) >= 40:
            out.text = svc.ocr.read(loaders.jpeg_bytes(image))
    out.text = (out.text or "")[: loaders.MAX_TEXT_CHARS]


# --------------------------------------------------------------------------
# Main-thread half (owns the connection)
# --------------------------------------------------------------------------
def _crop_face(image: Any, bbox: tuple[float, float, float, float], size: int = 160, margin: float = 0.35) -> Any:
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) * (1 + 2 * margin) / 2
    return image.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half))).resize((size, size))


@dataclass
class ResultWriter:
    conn: sqlite3.Connection
    paths: Paths
    guard: WriteGuard
    embedder: ImageEmbedder | None = None
    batch_size: int = 16
    faces_added: int = 0
    _batch: list[tuple[int, Any]] = field(default_factory=list)

    def apply(self, res: WorkResult) -> None:
        job, now = res.job, time.time()
        if res.error:
            if job.stage == STAGE_INDEX:  # a file we cannot even decode: exclude it from later passes
                self.conn.execute("UPDATE items SET error=?, indexed_at=? WHERE id=?", (res.error[:500], now, job.id))
            else:  # non-fatal: remember why and never retry endlessly
                self._note(job.id, f"{job.stage}: {res.error}"[:300])
                self.conn.execute(f"UPDATE items SET {_DONE_COL[job.stage]}=1 WHERE id=?", (job.id,))
            return
        if job.stage == STAGE_INDEX:
            self._apply_index(res, now)
        elif job.stage == STAGE_FACES:
            self._apply_faces(res)
        elif job.stage == STAGE_OCR:
            self._apply_ocr(res)

    # ------------------------------------------------------------------
    def _apply_index(self, res: WorkResult, now: float) -> None:
        job, meta = res.job, res.meta
        if meta is not None:
            place_label, place_text = res.place or (None, "")
            rel = self.conn.execute("SELECT rel_path FROM items WHERE id=?", (job.id,)).fetchone()
            self.conn.execute(
                "UPDATE items SET width=?, height=?, taken_at=?, camera=?, lens=?, gps_lat=?, gps_lon=?, "
                "place=?, place_text=?, meta_text=?, exif_json=?, thumb=?, preview=?, meta_done=1, "
                "error=NULL, indexed_at=?, taken_exif=? WHERE id=?",
                (
                    meta.width, meta.height, meta.taken_at, meta.camera, meta.lens, meta.gps_lat, meta.gps_lon,
                    place_label, place_text, meta_text_for(rel[0] if rel else "", meta.camera, meta.lens),
                    json.dumps(meta.details, default=str), thumb_rel(job.id), preview_rel(job.id), now, int(res.taken_exif), job.id,
                ),
            )  # fmt: skip
        if res.tensor is not None:
            self._batch.append((job.id, res.tensor))
            if len(self._batch) >= self.batch_size:
                self.flush_embeddings()

    def flush_embeddings(self) -> None:
        if not self._batch or self.embedder is None:
            self._batch.clear()
            return
        vectors = self.embedder.embed_prepared([t for _, t in self._batch])
        self.conn.executemany(
            "INSERT OR REPLACE INTO embeddings(item_id, vec) VALUES (?,?)",
            [(i, v.astype(np.float16).tobytes()) for (i, _), v in zip(self._batch, vectors, strict=True)],
        )
        self.conn.executemany("UPDATE items SET clip_done=1 WHERE id=?", [(i,) for i, _ in self._batch])
        meta_set(self.conn, "embed_version", str(time.time()))
        self._batch.clear()

    def _apply_faces(self, res: WorkResult) -> None:
        job = res.job
        self.conn.execute("DELETE FROM faces WHERE item_id=?", (job.id,))
        if res.faces and res.face_image is not None:
            width, height = res.face_image.size
            for face in res.faces:
                x1, y1, x2, y2 = face.bbox
                cur = self.conn.execute(
                    "INSERT INTO faces(item_id, x1, y1, x2, y2, score, px, emb) VALUES (?,?,?,?,?,?,?,?)",
                    (job.id, x1 / width, y1 / height, x2 / width, y2 / height, face.score,
                     int(min(x2 - x1, y2 - y1)), face.embedding.astype(np.float32).tobytes()),
                )  # fmt: skip
                face_id = cur.lastrowid or 0
                rel = face_rel(face_id)
                dest = self.guard.check(self.paths.data / rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                _crop_face(res.face_image, face.bbox).save(dest, "JPEG", quality=88)
                self.conn.execute("UPDATE faces SET crop=? WHERE id=?", (rel, face_id))
                self.faces_added += 1
        self.conn.execute("UPDATE items SET faces_done=1 WHERE id=?", (job.id,))

    def _apply_ocr(self, res: WorkResult) -> None:
        text = (res.text or "").strip()
        self.conn.execute("DELETE FROM fts WHERE rowid=?", (res.job.id,))
        if text:
            self.conn.execute("INSERT INTO fts(rowid, text) VALUES (?,?)", (res.job.id, text))
        self.conn.execute("UPDATE items SET ocr_done=1, ocr_chars=? WHERE id=?", (len(text), res.job.id))

    def _note(self, item_id: int, note: str) -> None:
        self.conn.execute("UPDATE items SET notes=? WHERE id=?", (note, item_id))

    def finish(self) -> None:
        self.flush_embeddings()
        self.conn.commit()


_DONE_COL = {STAGE_INDEX: "meta_done", STAGE_FACES: "faces_done", STAGE_OCR: "ocr_done"}
