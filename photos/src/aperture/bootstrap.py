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

import numpy as np
from images.engine import Engine
from images.jsonutil import extract_json

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

log = logging.getLogger(__name__)


class AppContext(Engine):
    """The engine plus the chat: the agent, its language model and the warm-up."""

    # -- settings ---------------------------------------------------------

    # -- ML adapters (imported lazily: heavy) -----------------------------

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

        from images.indexing.progress import ScanLock

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
        from images.search.visual import VisualSearch

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
        from images.search.geo import fill_missing_places

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

    def warm_problem(self) -> str:
        """Why the search is not ready, if something failed (shown on the page instead of 'warming up' forever)."""
        if self.embedder_error:
            return self.embedder_error
        return "; ".join(f"{name}: {error}" for name, error in self.warm_errors.items())

    def search_ready(self) -> bool:
        """True once the photo index and the image-search model are loaded (the first search is then instant)."""
        return self._index is not None and self._embedder is not None and (self._replica is not None or self._replica_tried)

    # -- scanning ---------------------------------------------------------

    def _prime_photo_list(self) -> None:
        """Read the list of live photos once at start-up (it is remembered until the library file changes)."""
        from images.search.metadata import TEXT_COLUMNS, _text_column, all_ids

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
