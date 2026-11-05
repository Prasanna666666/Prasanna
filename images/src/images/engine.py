"""The picture engine's working parts: where things are, the index, the models that read a picture, and the scan that fills the index.

Any app that needs pictures understood builds an Engine (the Documents service runs it for every picture it receives; Photos shows what it found).
It knows nothing about chat or screens."""

from __future__ import annotations

import logging
import threading
from typing import Any

from .config import Paths, Settings, default_paths
from .db import Database, meta_get
from .indexing.pipeline import STAGE_FACES, STAGE_INDEX, STAGE_OCR, Services
from .indexing.runner import Scanner
from .ml.protocols import ImageEmbedder
from .search.embeddings import EmbeddingIndex
from .search.geo import GeoIndex

log = logging.getLogger(__name__)


class ServiceUnavailableError(RuntimeError):
    """A required ML component cannot be loaded (message is user-facing)."""


class Engine:
    """Process-wide handles: settings, the database, the models, the scan. Safe to share between threads."""

    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or default_paths()
        self.settings = Settings.load(self.paths)
        self.db = Database(self.paths.db)
        self._lock = threading.Lock()
        self._index: EmbeddingIndex | None = None
        self._index_version: str | None = None
        self._embedder: ImageEmbedder | None = None
        self.embedder_error: str = ""
        self.warm_errors: dict[str, str] = {}
        self._geo: GeoIndex | None = None
        self._geo_tried = False

    def reload_settings(self) -> Settings:
        self.settings = Settings.load(self.paths)
        return self.settings

    def build_embedder(self) -> ImageEmbedder:
        from images.ml.clip import OpenClipEmbedder

        s = self.settings
        try:
            return OpenClipEmbedder(s.clip_model, s.clip_pretrained, self.paths.clip_cache)
        except Exception as exc:
            raise ServiceUnavailableError(
                f"CLIP model unavailable ({exc}). Run `aperture fetch-models` once while online."
            ) from exc

    def search_embedder(self) -> ImageEmbedder | None:
        """Shared embedder for query encoding (loaded on first use)."""
        with self._lock:
            if self._embedder is None and not self.embedder_error:
                try:
                    self._embedder = self.build_embedder()
                except ServiceUnavailableError as exc:
                    self.embedder_error = str(exc)
            return self._embedder

    def ready_embedder(self) -> ImageEmbedder | None:
        """The picture-search model for a question: only if it is already loaded. Loading it takes 20 to 60 s (torch and the weights come from the
        external drive), so a question never waits for it: it answers from everything else and the model finishes loading in the background."""
        if self._embedder is None and not self.embedder_error and not getattr(self, "_loading", False):
            self._loading = True
            threading.Thread(target=self.search_embedder, name="load-search-model", daemon=True).start()
        return self._embedder

    def memo(self, key: str, ttl: float, fn):
        """Remember a slow, request-independent lookup (a table scan on the external drive) for `ttl` seconds."""
        import time

        store = self.__dict__.setdefault("_memo_store", {})
        with self._lock:
            hit = store.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
        value = fn()
        with self._lock:
            store[key] = (time.monotonic(), value)
        return value

    def embedding_index(self) -> EmbeddingIndex:
        """Cached index, rebuilt automatically when a scan changes embeddings."""
        conn = self.db.connect()
        try:
            version = meta_get(conn, "embed_version", "0")
            with self._lock:
                if self._index is None or version != self._index_version:
                    self._index = EmbeddingIndex.from_db(conn)
                    self._index_version = version
                return self._index
        finally:
            conn.close()

    def services_for_stage(self, stage: str) -> Services:
        s = self.settings
        if stage == STAGE_INDEX:
            geo = GeoIndex.load(self.paths)
            embedder = self.build_embedder() if s.stages.clip else None
            return Services(embedder=embedder, geo=geo)
        if stage == STAGE_FACES:
            from images.ml.faces import OnnxFaceAnalyzer

            try:
                faces = OnnxFaceAnalyzer(
                    self.paths.face_models,
                    det_size=s.face_det_size,
                    det_thresh=s.face_det_thresh,
                    use_coreml=s.face_use_coreml,
                )
            except Exception as exc:
                raise ServiceUnavailableError(f"Face models unavailable ({exc}).") from exc
            return Services(faces=faces)
        if stage == STAGE_OCR:
            from images.ml.ocr import TesseractOCR, VisionOCR, tesseract_available, vision_available

            if vision_available():
                return Services(ocr=VisionOCR())
            if tesseract_available():
                return Services(ocr=TesseractOCR())
            log.warning(
                "No text reader (Apple Vision or Tesseract) is available: images will not be OCR'd (PDFs/text still are)."
            )
            return Services()
        return Services()

    def scanner(self, stop: threading.Event | None = None) -> Scanner:
        return Scanner(self.paths, self.settings, self.db, self.services_for_stage, stop)

    def geo(self) -> GeoIndex | None:
        """Offline place data, loaded once (None until fetched)."""
        with self._lock:
            if self._geo is None and not self._geo_tried:
                self._geo_tried = True
                self._geo = GeoIndex.load(self.paths)
            return self._geo

    _replica: Any = None

    _replica_tried: bool = False  # the in-memory copy was attempted (built, or it failed and questions read the drive file)

    def question_db(self) -> Any:
        """The connection a question reads: the in-memory copy when it is ready, otherwise the library file."""
        if self._replica is not None:
            conn = self._replica.connect()
            if conn is not None:
                return conn
        return self.db.connect()

    def _build_replica(self) -> None:
        from images.search.replica import Replica

        replica = Replica(self.paths.db)
        try:
            if replica.build():
                self._replica = replica
                replica.keep_fresh()
        finally:
            self._replica_tried = True

    def ready_geo(self) -> GeoIndex | None:
        """The place list for a question: only if already loaded (loading it took 25 s from the drive). It loads at start-up, never during a question."""
        if self._geo is None and not self._geo_tried and not getattr(self, "_geo_loading", False):
            self._geo_loading = True
            threading.Thread(target=self.geo, name="load-places", daemon=True).start()
        return self._geo
