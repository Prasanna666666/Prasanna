"""Composition root: wires settings, database, ML adapters and the agent.

This is the only module that knows about concrete ML classes.  Everything else
receives its collaborators through constructors, which keeps the rest of the
code base testable and replaceable.
"""

from __future__ import annotations

from typing import Any

from collections.abc import Callable
from functools import lru_cache

import logging
import threading
from datetime import date

import numpy as np

from .agent.captions import describe_item
from .agent.executor import Executor
from .agent.jsonutil import extract_json
from .agent.knowledge import answer as answer_question
from .agent.knowledge import gather_facts
from .agent.llm import LLMError, OllamaClient, OllamaVision
from .agent.loop import AgentLoop, Toolbox
from .agent.planner import Planner
from . import library as lib
from .agent.toolagent import ToolAgent, close_matches
from .agent.service import DATE_SCHEMA, DATE_SYSTEM, CHAT_MAX_TOKENS, CHAT_SYSTEM, ROUTER_SCHEMA, ROUTER_SYSTEM, Agent, AgentService
from .config import Paths, Settings, default_paths
from .db import Database, meta_get
from .indexing.pipeline import STAGE_FACES, STAGE_INDEX, STAGE_OCR, Services
from .indexing.runner import Scanner
from .ml.protocols import ImageEmbedder
from .people.repository import named_people, resolve_name
from .search.embeddings import EmbeddingIndex
from .search.geo import GeoIndex
from .search.quick import probe

log = logging.getLogger(__name__)
MAX_PHOTOS_TO_LOOK_AT = 3  # vision is slow: only look when the question concerns a few photos


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
            if name in ("AI model", "image search model") and ScanLock(self.paths).running(verify=True):
                log.debug("warm-up: scan running, not loading the %s", name)
                return
            try:
                step()
            except Exception as exc:
                log.debug("warm-up: %s failed", name, exc_info=True)
                self.warm_errors[name] = f"{type(exc).__name__}: {exc}"

        def drive_reads() -> None:  # reading the index and the library facts waits on the drive: do it while the model loads
            try:
                run("photo index", self.embedding_index)
                run("library facts", self._prime_library_facts)
            finally:
                reads_done.set()

        def work() -> None:
            threading.Thread(target=drive_reads, name="warm-up-drive", daemon=True).start()
            run("AI model", lambda: self.llm().warm())
            reads_done.wait()
            run("image search model", self.search_embedder)  # the slowest model goes last

        threading.Thread(target=work, name="warm-up", daemon=True).start()

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
        return self._index is not None and self._embedder is not None

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
            return value if value in ("chat", "simple") else "photos"

        return lambda request, has_previous: route(" ".join(request.split()), has_previous)

    def service(self) -> AgentService:
        """The plan runner behind the agent (router, planner, executor)."""
        self.agent()
        return self._service

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
            def load() -> list[str]:
                conn = self.db.connect()
                try:
                    return [name for _, name in named_people(conn)]
                finally:
                    conn.close()

            return self.memo("people", 60.0, load)

        def library_facts(request: str) -> str:
            def static_facts() -> tuple[list[str], str | None, str | None]:  # two table scans: the same for every request
                scan = self.db.connect()
                try:
                    found = [
                        r[0]
                        for r in scan.execute(
                            "SELECT place FROM items WHERE place IS NOT NULL AND place<>'' AND missing=0 "
                            "GROUP BY place ORDER BY COUNT(*) DESC LIMIT 25"
                        )
                    ]
                    lo, hi = scan.execute("SELECT MIN(taken_at), MAX(taken_at) FROM items WHERE missing=0").fetchone()
                    return found, lo, hi
                finally:
                    scan.close()

            places, first, last = self.memo("static_facts", 300.0, static_facts)
            conn = self.db.connect()
            try:

                def person_photos(phrase: str) -> int:
                    ids = resolve_name(conn, phrase)
                    if not ids:
                        return 0
                    marks = ",".join("?" * len(ids))
                    return int(
                        conn.execute(f"SELECT COUNT(DISTINCT item_id) FROM faces WHERE person_id IN ({marks})", ids).fetchone()[0]
                    )

                evidence = probe(conn, request, person_photos)
            finally:
                conn.close()
            lines = []
            if places:
                lines.append("PLACES IN THIS LIBRARY: " + "; ".join(places))
            if first and last:
                lines.append(f"PHOTOS SPAN: {str(first)[:10]} to {str(last)[:10]}")
            if evidence:
                lines.append(evidence)
            return "\n".join(lines)

        def answerer(question: str, previous: np.ndarray | None) -> str:
            conn = self.db.connect()
            try:
                facts = gather_facts(conn, self.paths, previous)
                if previous is not None and 0 < len(previous) <= MAX_PHOTOS_TO_LOOK_AT and self.needs_to_see(question):
                    seen = []
                    for i, item_id in enumerate(previous.tolist(), 1):
                        try:
                            seen.append(
                                f"- photo {i}: {describe_item(conn, self.paths, self.describer(), self.settings.vision_model, int(item_id), question)}"
                            )
                        except LLMError as exc:
                            seen.append(f"- photo {i}: could not look at it ({exc})")
                    facts += "\nWHAT THE VISION MODEL SAW IN THE PREVIOUS PHOTOS:\n" + "\n".join(seen)
            finally:
                conn.close()
            return answer_question(self.llm().complete_text, question, facts)

        def _chat_system() -> str:
            return f"Today's date is {date.today():%A %d %B %Y}.\n" + CHAT_SYSTEM

        def chatter(request: str, history: list[tuple[str, str]]) -> str:
            turns = [{"role": role, "content": text} for role, text in history[-8:] if role in ("user", "assistant") and text]
            return self.llm().complete_chat(_chat_system(), [*turns, {"role": "user", "content": request}], max_tokens=CHAT_MAX_TOKENS)

        def chat_stream(request: str, history: list[tuple[str, str]]):
            turns = [{"role": role, "content": text} for role, text in history[-8:] if role in ("user", "assistant") and text]
            return self.llm().stream_chat(_chat_system(), [*turns, {"role": "user", "content": request}], max_tokens=CHAT_MAX_TOKENS)

        def library_context(request: str) -> str:
            """RAG: facts from the user's own library that matter for THIS request (matching places and people, the date span)."""
            lines = [library_facts(request)]

            def count() -> str:
                conn = self.db.connect()
                try:
                    cov = lib.coverage(conn)
                    return f"{cov.total:,} files, {cov.indexed:,} indexed"
                finally:
                    conn.close()

            lines.append("LIBRARY SIZE: " + self.memo("coverage_text", 60.0, count))
            people = people_names()
            if people:
                lines.append("PEOPLE FOUND: " + ", ".join(people[:40]))
            return "\n".join(line for line in lines if line)

        def date_step(request: str):
            """A short, focused model call: the time expression in the message (if any), as real date fields."""
            from .agent.schema import plan_from_raw

            answer = self.llm().complete_json(DATE_SYSTEM, request, DATE_SCHEMA, max_tokens=60)
            try:
                raw = extract_json(answer)
            except Exception:  # unreadable answer: treat as "no time expression"; an extra check must never stop a search
                raw = None
            if not isinstance(raw, dict):
                return "", plan_from_raw({})[0].date
            date_fields = {k: raw[k] for k in ("year", "month", "season", "relative", "ago", "unit", "through") if k in raw}
            return str(raw.get("phrase") or "").strip(), plan_from_raw({"intent": "find", "date": date_fields})[0].date

        def reviser(request: str, plan: Any, feedback: str) -> Any:
            """Agent step: the search found nothing. Show the model what it tried and why it failed, and ask for a better plan."""
            import dataclasses
            import json

            from .agent.planner import plan_schema, plan_style, system_prompt
            from .agent.schema import plan_from_raw

            user = (
                f"{library_context(request)}\nUser: {request}\n\n"
                f"YOUR LAST PLAN FOUND NOTHING.\nPlan: {json.dumps(dataclasses.asdict(plan), default=str)}\nWhat happened: {feedback}\n"
                "Write a DIFFERENT plan that finds what the user meant. Compare each query with the real places, people and folders listed above: "
                "use a name exactly as listed, widen a place to its country or region, use scope \"library\" unless they clearly mean the earlier results, "
                "or drop a wrong clause. Output ONLY the JSON object."
            )
            style = plan_style()
            raw = extract_json(self.llm().complete_json(system_prompt(style), user, plan_schema(style)))
            return plan_from_raw(raw)[0] if isinstance(raw, dict) else None

        def probe_term(term: str) -> dict[str, Any]:
            """The probe tool: where does this word occur in the library? Counts per possible meaning, from the library itself."""
            from .people.repository import resolve_name
            from .search.metadata import path_ids, place_ids
            from .search.text import search_text_ids

            conn = self.db.connect()
            try:
                counts = {
                    "as_place": len(place_ids(conn, term)),
                    "as_folder_or_file_name": len(path_ids(conn, term)),
                    "as_words_written_in_photos": len(search_text_ids(conn, term)),
                    "as_person": len(resolve_name(conn, term)),
                }
            finally:
                conn.close()
            out: dict[str, Any] = {"term": term, **counts}
            if not any(counts.values()):
                out["similar_places"] = lookup("place", term)
                out["note"] = "no exact match anywhere: it may be something to look for in the pictures, a date, or a place spelled differently"
            return out

        def inspect_results(ids: list[int]) -> dict[str, Any]:
            """The inspect_results tool: when (date periods), where (places) and in which folders the given photos were taken."""
            from collections import Counter
            from datetime import date as _date, timedelta

            conn = self.db.connect()
            try:
                rows: list[tuple[Any, Any, Any]] = []
                for start in range(0, len(ids), 500):
                    part = ids[start : start + 500]
                    rows += conn.execute(
                        f"SELECT substr(taken_at,1,10), place, rel_path FROM items WHERE id IN ({','.join('?' * len(part))})", part
                    ).fetchall()
            finally:
                conn.close()
            days = sorted({_date.fromisoformat(d) for d, _, _ in rows if d and len(d) == 10})
            periods: list[list[Any]] = []
            for day in days:
                if periods and day - periods[-1][1] <= timedelta(days=5):
                    periods[-1][1] = day
                    periods[-1][2] += 1
                else:
                    periods.append([day, day, 1])
            counts = Counter(d for d, _, _ in rows if d)
            sized = [{"date_from": a.isoformat(), "date_to": b.isoformat(),
                      "photos": sum(c for d, c in counts.items() if a.isoformat() <= d <= b.isoformat())} for a, b, _ in periods]
            sized.sort(key=lambda p: -p["photos"])
            places = Counter(p for _, p, _ in rows if p)
            folders = Counter(r.split("/")[0] for _, _, r in rows if r and "/" in r)
            return {"photos": len(rows), "date_periods": sized[:6], "places": places.most_common(5), "folders": folders.most_common(5)}

        def overview(previous_ids: Any) -> str:
            """The library_overview tool: plain facts for the model to read."""
            conn = self.db.connect()
            try:
                return gather_facts(conn, self.paths, previous_ids)
            finally:
                conn.close()

        def read_text(ids: list[int]) -> list[dict[str, Any]]:
            """The read_photo_text tool: the words found inside photos (OCR), for the model to answer from."""
            conn = self.db.connect()
            try:
                items = lib.items_by_ids(conn, ids)
                out = []
                for i in ids:
                    text = " ".join(lib.item_text(conn, i, 900).split())
                    if text:
                        item = items.get(i)
                        out.append({"photo": i, "date": (item.taken_at or "")[:10] if item else "", "place": item.place if item else "", "text": text})
                return out
            finally:
                conn.close()

        def look(ids: list[int], question: str) -> list[dict[str, Any]]:
            """The look_at_photos tool: the vision model answers a question about a few photos (descriptions are remembered)."""
            conn = self.db.connect()
            try:
                answers = []
                for i in ids:
                    try:
                        answers.append({"photo": i, "answer": describe_item(conn, self.paths, self.describer(), self.settings.vision_model, i, question)})
                    except LLMError as exc:
                        answers.append({"photo": i, "error": str(exc)})
                return answers
            finally:
                conn.close()

        def lookup(kind: str, text: str) -> list[str]:
            """The look_up tool: which places, people or folders really exist in this library."""
            def distinct(sql: str) -> list[str]:
                conn = self.db.connect()
                try:
                    return [str(r[0]) for r in conn.execute(sql) if r[0]]
                finally:
                    conn.close()

            if kind == "person":
                return close_matches(people_names(), text)
            if kind == "place":
                places = self.memo("all_places", 300.0, lambda: distinct("SELECT DISTINCT place FROM items WHERE place IS NOT NULL AND place<>'' AND missing=0"))
                return close_matches(places, text)
            if kind == "folder":
                folders = self.memo("all_folders", 300.0, lambda: distinct(
                    "SELECT DISTINCT substr(rel_path, 1, instr(rel_path, '/') - 1) FROM items WHERE instr(rel_path, '/') > 0 AND missing=0"))
                return close_matches(folders, text)
            return []

        if not self.settings.agentic:
            service = AgentService(
                Planner(self.llm()), make_executor, people_names, today=date.today, library_facts=library_facts,
                answerer=answerer, chatter=chatter, chat_stream=chat_stream, router=self.router(),
                fast_search=self.settings.fast_search, rescue=self.settings.rescue_search, date_step=date_step, reviser=reviser,
            )
            self._service = service  # the search executor the agent uses (tests exercise it directly)
            return ToolAgent(self.llm(), service, library_context, overview=overview, lookup=lookup, read_text=read_text, look=look, probe=probe_term, inspect=inspect_results)
        vision = OllamaVision(self.settings.ollama_url, self.settings.vision_model, timeout=120.0)

        def toolbox(previous: np.ndarray | None) -> Toolbox:
            return Toolbox(
                self.db.connect(), self.paths, self.settings, make_executor,
                self.embedding_index, self.search_embedder, vision, previous,
            )  # fmt: skip

        return AgentLoop(self.llm(), toolbox, people_names, max_steps=self.settings.agent_max_steps, today=date.today)
