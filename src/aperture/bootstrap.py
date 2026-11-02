"""Composition root: wires settings, database, ML adapters and the agent.

This is the only module that knows about concrete ML classes.  Everything else
receives its collaborators through constructors, which keeps the rest of the
code base testable and replaceable.
"""

from __future__ import annotations

import logging
import threading
from datetime import date

import numpy as np

from .agent.executor import Executor
from .agent.llm import OllamaClient, OllamaVision
from .agent.loop import AgentLoop, Toolbox
from .agent.planner import Planner
from .agent.service import Agent, AgentService
from .config import Paths, Settings, default_paths
from .db import Database, meta_get
from .indexing.pipeline import STAGE_FACES, STAGE_INDEX, STAGE_OCR, Services
from .indexing.runner import Scanner
from .ml.protocols import ImageEmbedder
from .people.repository import named_people
from .search.embeddings import EmbeddingIndex
from .search.geo import GeoIndex

log = logging.getLogger(__name__)


class ServiceUnavailableError(RuntimeError):
    """A required ML component cannot be loaded (message is user-facing)."""


class AppContext:
    """Process-wide handles.  Safe to share between Streamlit sessions."""

    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or default_paths()
        self.settings = Settings.load(self.paths)
        self.db = Database(self.paths.db)
        self._lock = threading.Lock()
        self._index: EmbeddingIndex | None = None
        self._index_version: str | None = None
        self._embedder: ImageEmbedder | None = None
        self.embedder_error: str = ""
        self._geo: GeoIndex | None = None
        self._geo_tried = False

    # -- settings ---------------------------------------------------------
    def reload_settings(self) -> Settings:
        self.settings = Settings.load(self.paths)
        return self.settings

    # -- ML adapters (imported lazily: heavy) -----------------------------
    def build_embedder(self) -> ImageEmbedder:
        from .ml.clip import OpenClipEmbedder

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

    def warm_up(self) -> None:
        """Load everything a first question needs (AI model, search model, index) in the background."""
        import threading

        def work() -> None:
            import time

            from .indexing.progress import ScanLock

            try:
                self.llm().warm()
            except Exception:
                log.debug("AI warm-up failed", exc_info=True)
            while ScanLock(self.paths).running():  # a scan needs the memory more: wait for it
                time.sleep(10)
            for step in (self.search_embedder, self.embedding_index):
                try:
                    step()
                except Exception:
                    log.debug("warm-up step failed", exc_info=True)

        threading.Thread(target=work, name="warm-up", daemon=True).start()

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

    # -- scanning ---------------------------------------------------------
    def services_for_stage(self, stage: str) -> Services:
        s = self.settings
        if stage == STAGE_INDEX:
            geo = GeoIndex.load(self.paths)
            embedder = self.build_embedder() if s.stages.clip else None
            return Services(embedder=embedder, geo=geo)
        if stage == STAGE_FACES:
            from .ml.faces import OnnxFaceAnalyzer

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
            from .ml.ocr import VisionOCR, vision_available

            if not vision_available():
                log.warning("Apple Vision is not available: images will not be OCR'd (PDFs/text still are).")
                return Services()
            return Services(ocr=VisionOCR())
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

    # -- agent ------------------------------------------------------------
    def llm(self) -> OllamaClient:
        return OllamaClient(self.settings.ollama_url, self.settings.ollama_model)

    def agent(self) -> Agent:
        def make_executor() -> Executor:
            return Executor(
                self.db.connect(),
                self.embedding_index,
                self.search_embedder,
                strictness=self.settings.visual_strictness,
                geo_provider=self.geo,
            )

        def people_names() -> list[str]:
            conn = self.db.connect()
            try:
                return [name for _, name in named_people(conn)]
            finally:
                conn.close()

        if not self.settings.agentic:
            return AgentService(Planner(self.llm()), make_executor, people_names, today=date.today)
        vision = OllamaVision(self.settings.ollama_url, self.settings.vision_model, timeout=120.0)

        def toolbox(previous: np.ndarray | None) -> Toolbox:
            return Toolbox(
                self.db.connect(), self.paths, self.settings, make_executor,
                self.embedding_index, self.search_embedder, vision, previous,
            )  # fmt: skip

        return AgentLoop(self.llm(), toolbox, people_names, max_steps=self.settings.agent_max_steps, today=date.today)
