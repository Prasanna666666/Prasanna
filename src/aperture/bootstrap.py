"""Composition root: wires settings, database, ML adapters and the agent.

This is the only module that knows about concrete ML classes.  Everything else
receives its collaborators through constructors, which keeps the rest of the
code base testable and replaceable.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import date
from functools import lru_cache
from typing import Any

import numpy as np

from .agent.jsonutil import extract_json
from .agent.llm import OllamaClient, OllamaVision
from .agent.loop import AgentLoop, Toolbox
from .agent.planner import Planner
from .agent.service import (
    ROUTER_SCHEMA,
    ROUTER_SYSTEM,
    Agent,
    AgentService,
)
from .agent.toolagent import ToolAgent
from .agent_parts import AgentParts
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
        self.warm_errors: dict[str, str] = {}
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

    def ready_embedder(self) -> ImageEmbedder | None:
        """The picture-search model for a question: only if it is already loaded. Loading it takes 20 to 60 s (torch and the weights come from the
        external drive), so a question never waits for it: it answers from everything else and the model finishes loading in the background."""
        if self._embedder is None and not self.embedder_error and not getattr(self, "_loading", False):
            self._loading = True
            threading.Thread(target=self.search_embedder, name="load-search-model", daemon=True).start()
        return self._embedder

    def describer(self) -> OllamaVision:
        return OllamaVision(self.settings.ollama_url, self.settings.vision_model, timeout=180.0)

    def needs_to_see(self, question: str) -> bool:
        """Ask the AI whether this question is about what is visible in the photos themselves."""
        schema = {"type": "object", "properties": {"needs_to_look": {"type": "boolean"}}, "required": ["needs_to_look"]}
        system = (
            "Decide whether answering the user's question requires LOOKING at the picture contents "
            "(what is shown, colours, objects, people's clothing, mood). Statistics, counts, dates, places, "
            "file names and move/index status do NOT. Reply as JSON."
        )
        try:
            raw = self.llm().complete_json(system, question, schema)
            return bool(extract_json(raw).get("needs_to_look"))
        except Exception:
            return False

    def warm_up(self) -> None:
        """Preload in the background so the first question is not the slow one: photo index, image-search model, AI model.

        Models are only preloaded while no scan runs: a scan plus both models at once pushes an 8 GB Mac into swap."""
        import threading

        from .indexing.progress import ScanLock

        reads_done = threading.Event()

        def run(name: str, step) -> None:
            if name in ("AI model", "image search model", "search warm-up") and ScanLock(self.paths).running(verify=True):
                log.debug("warm-up: scan running, not loading the %s", name)
                return
            try:
                step()
            except Exception as exc:
                log.debug("warm-up: %s failed", name, exc_info=True)
                self.warm_errors[name] = f"{type(exc).__name__}: {exc}"

        def drive_reads() -> None:  # reading the index and the library facts waits on the drive: do it while the model loads
            try:
                if hasattr(self, "db"):
                    run(
                        "question copy", self._build_replica
                    )  # first: it is what makes every question fast, and nothing else should compete for the drive
                    run("photo list", self._prime_photo_list)
                run("photo index", self.embedding_index)
                if hasattr(self, "geo"):
                    run("place data", self.geo)
                run("place names", self._fill_places)
                run("library facts", self._prime_library_facts)
            finally:
                reads_done.set()

        def work() -> None:
            threading.Thread(target=drive_reads, name="warm-up-drive", daemon=True).start()
            run(
                "image search model", self.search_embedder
            )  # first: loading it while the chat model answers would slow the chat down
            reads_done.wait()
            if hasattr(self, "_warm_search"):
                run(
                    "search warm-up", self._warm_search
                )  # the first real search compiles GPU code for several seconds: do it now, not on your first question
            run(
                "AI model", self.warm_ai if hasattr(self, "warm_ai") else lambda: self.llm().warm()
            )  # last, so it is hot when you start

        threading.Thread(target=work, name="warm-up", daemon=True).start()

    def _warm_search(self) -> None:
        """Run one real picture search so the first one a person asks is not the slow one."""
        from .search.visual import VisualSearch

        embedder = self.search_embedder()
        index = self.embedding_index()
        if embedder is not None and len(index):
            VisualSearch(index, embedder).search("a photo of people")

    def warm_ai(self) -> None:
        agent = self.agent()
        if hasattr(agent, "warm"):
            agent.warm()  # model + the real instructions and tools
        else:
            self.llm().warm()

    def _fill_places(self) -> None:
        """Name photos that have GPS but no place yet (cheap: no file is read)."""
        from .search.geo import fill_missing_places

        geo = self.geo()
        if geo is None:
            return
        conn = self.db.connect()
        try:
            fill_missing_places(conn, geo)
        finally:
            conn.close()

    def _prime_library_facts(self) -> None:
        """Run the first, slow library lookups now (while the app warms up) so the first question does not pay for them."""
        agent = self.agent()
        context = getattr(agent, "_context", None)  # the agent's retrieval step: places, years, library size, people
        if callable(context):
            context("photos")

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

    def warm_problem(self) -> str:
        """Why the search is not ready, if something failed (shown on the page instead of 'warming up' forever)."""
        if self.embedder_error:
            return self.embedder_error
        return "; ".join(f"{name}: {error}" for name, error in self.warm_errors.items())

    def search_ready(self) -> bool:
        """True once the photo index and the image-search model are loaded (the first search is then instant)."""
        return self._index is not None and self._embedder is not None and (self._replica is not None or self._replica_tried)

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
            from .ml.ocr import TesseractOCR, VisionOCR, tesseract_available, vision_available

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
        from .search.replica import Replica

        replica = Replica(self.paths.db)
        try:
            if replica.build():
                self._replica = replica
                replica.keep_fresh()
        finally:
            self._replica_tried = True

    def _prime_photo_list(self) -> None:
        """Read the list of live photos once at start-up (it is remembered until the library file changes)."""
        from .search.metadata import TEXT_COLUMNS, _text_column, all_ids

        conn = self.db.connect()
        try:
            all_ids(conn)
            for column in TEXT_COLUMNS:
                _text_column(conn, column)
            # One practice search on a real place, so the counts and GPS positions a question needs are already in memory for your first one.
            row = conn.execute("SELECT place FROM items WHERE missing=0 AND place<>'' LIMIT 1").fetchone()
            if row:
                from .agent.executor import Executor
                from .agent.schema import Clause, Plan

                term = str(row[0]).split(",")[0].strip()
                executor = Executor(conn, self.embedding_index, self.ready_embedder, geo_provider=self.ready_geo)
                executor.explore(Plan(intent="find", clauses=(Clause(engines=("place", "path"), query=term),)))
        finally:
            conn.close()

    def ready_geo(self) -> GeoIndex | None:
        """The place list for a question: only if already loaded (loading it took 25 s from the drive). It loads at start-up, never during a question."""
        if self._geo is None and not self._geo_tried and not getattr(self, "_geo_loading", False):
            self._geo_loading = True
            threading.Thread(target=self.geo, name="load-places", daemon=True).start()
        return self._geo

    # -- agent ------------------------------------------------------------
    def llm(self) -> OllamaClient:
        return OllamaClient(self.settings.ollama_url, self.settings.ollama_model)

    def router(self) -> Callable[[str, bool], str]:
        """Tiny, fast classifier: 'photos' (about the library) or 'chat'. Anything unclear counts as photos."""

        @lru_cache(maxsize=256)  # the same message is answered instantly the second time
        def route(message: str, has_previous: bool) -> str:
            user = f"EARLIER RESULTS: {'yes' if has_previous else 'no'}\nMessage: {message}"
            raw = self.llm().complete_json(ROUTER_SYSTEM, user, ROUTER_SCHEMA, max_tokens=16)
            try:
                value = extract_json(raw).get("route")
            except Exception:
                return "photos"
            return value if value in ("chat", "simple", "about") else "photos"

        return lambda request, has_previous: route(" ".join(request.split()), has_previous)

    def service(self) -> AgentService:
        """The plan runner behind the agent (router, planner, executor)."""
        self.agent()
        return self._service

    def agent(self) -> Agent:
        parts = AgentParts(self)

        if not self.settings.agentic:
            service = AgentService(
                Planner(self.llm()),
                parts.make_executor,
                parts.people_names,
                today=date.today,
                library_facts=parts.library_facts,
                answerer=parts.answerer,
                chatter=parts.chatter,
                chat_stream=parts.chat_stream,
                router=self.router(),
                fast_search=self.settings.fast_search,
                rescue=self.settings.rescue_search,
                date_step=parts.date_step,
                reviser=parts.reviser,
            )
            self._service = service  # the search executor the agent uses (tests exercise it directly)
            return ToolAgent(
                self.llm(),
                service,
                parts.library_context,
                overview=parts.overview,
                lookup=parts.lookup,
                read_text=parts.read_text,
                look=parts.look,
                probe=parts.probe_term,
                inspect=parts.inspect_results,
            )
        vision = OllamaVision(self.settings.ollama_url, self.settings.vision_model, timeout=120.0)

        def toolbox(previous: np.ndarray | None) -> Toolbox:
            return Toolbox(
                self.db.connect(), self.paths, self.settings, parts.make_executor,
                self.embedding_index, self.search_embedder, vision, previous,
            )  # fmt: skip

        return AgentLoop(self.llm(), toolbox, parts.people_names, max_steps=self.settings.agent_max_steps, today=date.today)
