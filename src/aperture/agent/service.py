"""High-level agent API used by the UI and CLI.

``AgentService.ask`` is the one entry point: plan -> execute -> explain.  Every
failure mode is converted into an :class:`AgentReply` (kind ``"error"``) so the
caller never has to catch exceptions to keep the interface alive.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

import numpy as np

from .executor import ClauseReport, Executor
from .llm import LLMError
from .planner import PlannerContext, Planner, PlanResult, PlanningError
from .schema import Clause, Plan

log = logging.getLogger(__name__)

Kind = Literal["results", "count", "export", "chat", "clarify", "error"]


@dataclass
class AgentReply:
    kind: Kind
    text: str
    ids: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    plan: Plan | None = None
    reports: list[ClauseReport] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    folder_name: str = ""  # for kind == "export"
    date_range: str = ""
    trace: list[dict[str, str]] = field(default_factory=list)  # what the agent did, step by step
    timings: dict[str, float] = field(default_factory=dict, repr=False, compare=False)  # seconds spent in each step
    groups: list[tuple[str, np.ndarray]] = field(default_factory=list, repr=False, compare=False)  # every reading of the query, best first
    stream: Any = field(default=None, repr=False, compare=False)  # chat replies: text arrives piece by piece (consumed by the UI)


class Agent(Protocol):
    def ask(
        self, request: str, previous_ids: np.ndarray | None = None, history: list[tuple[str, str]] | None = None
    ) -> AgentReply: ...


def describe_conditions(plan: Plan, date_range: str) -> str:
    parts = [c.label for c in plan.clauses]
    if date_range:
        parts.append(f"date {date_range}")
    if not plan.filters.is_empty:
        parts.append(plan.filters.describe())
    joiner = " OR " if plan.match == "any" else " AND "
    return joiner.join(parts) if parts else "everything in the library"


def explain_empty(reports: list[ClauseReport]) -> str:
    """Say which constraint made the result empty."""
    for report in reports:
        if report.matched == 0 and report.note != "excluded":
            return f"No photos match {report.label}."
    for report in reports:
        if report.remaining == 0:
            return f"No photo fits all of that. Nothing matches {report.label}."
    return "No photo matches."


def _only_plain_clauses(plan: Plan) -> bool:
    """Rescue ignores dates, filters and exclusions, so it only applies when the plan has none."""
    return not any(c.exclude for c in plan.clauses) and plan.date.is_empty and plan.filters.is_empty


CHAT_SYSTEM = (
    "You are Lumo, the assistant in a private photo app on the user's Mac. Chat naturally and warmly, in one or two short sentences of "
    "plain text, without emojis or lists. If the user is just being social, reply kindly and invite them to describe photos to find. "
    "For a general question, answer briefly and correctly. You cannot browse the web. You are not searching photos in this reply, "
    "so never claim to have found any.\n"
    "Examples:\n"
    "User: Hello\nLumo: Hi! What would you like to find in your photos today?\n"
    "User: How are you?\nLumo: Doing well, thanks for asking! Shall I look for some photos?\n"
    "User: What is a RAW file?\nLumo: A RAW file is the unprocessed data straight from a camera sensor, so it holds more detail to edit than a JPEG."
)
CHAT_MAX_TOKENS = 160  # short answers: it is a photo app, and short answers are also fast

ROUTER_SYSTEM = (
    "You route messages in a private photo app. Reply with JSON: {\"route\": \"simple\"}, {\"route\": \"photos\"} or {\"route\": \"chat\"}.\n"
    "simple = ONE subject to look for in the pictures themselves (an object, animal, food, scene or activity) and nothing else: no "
    "person's name, place, date or year, count, filter, 'not' or 'without', text written in a picture, and no earlier results. "
    "At most 4 words.\n"
    "photos = any other message about the user's photos or files or library: find, show, count, filter, copy or organize them, "
    "refine earlier results, or ask about them (how many, from which year, which people, places, indexing). Words like photos, pics, "
    "pictures, images, shots, selfies, albums, years and dates about their library mean photos. When in doubt, choose photos.\n"
    "chat = everything else: greetings, thanks, small talk, general knowledge, explanations, advice, writing help, questions about you.\n"
    "Examples: 'mountains' -> simple; 'birthday cake' -> simple; 'a cup of coffee' -> simple; 'sailing boats' -> simple; "
    "'photos of Anna at the beach' -> photos; 'sunset photos from 2023' -> photos; 'beach photos without people' -> photos; "
    "'find the invoice that mentions Acme' -> photos; 'how many pics from 2019' -> photos; 'only the ones from March' -> photos; "
    "'who is in my photos most' -> photos; 'what is RAW?' -> chat; 'thanks!' -> chat; 'tell me a joke' -> chat; 'what is 12 times 12' -> chat."
)
ROUTER_SCHEMA = {"type": "object", "properties": {"route": {"type": "string", "enum": ["simple", "photos", "chat"]}}, "required": ["route"]}
MAX_SIMPLE_WORDS = 4

DATE_SYSTEM = (
    "Find the time expression in the user's message. phrase = the exact words that express a time or period (for example 'last month', "
    "'in 2021', 'this summer', 'yesterday', 'March'), or an empty string if there is none. Fill year (like 2021), month (1-12), season or "
    "relative ONLY from that phrase and leave the other fields out. Never compute dates.\n"
    "Examples:\n"
    "'pics from last month' -> {\"phrase\": \"last month\", \"relative\": \"last_month\"}\n"
    "'what I shot in August 2019' -> {\"phrase\": \"August 2019\", \"year\": 2019, \"month\": 8}\n"
    "'skiing trip winter 2023' -> {\"phrase\": \"winter 2023\", \"year\": 2023, \"season\": \"winter\"}\n"
    "'pics from 2 months back' -> {\"phrase\": \"2 months back\", \"ago\": 2, \"unit\": \"month\"}\n"
    "'photos from the last 3 weeks' -> {\"phrase\": \"the last 3 weeks\", \"ago\": 3, \"unit\": \"week\", \"through\": true}\n"
    "'cats on the sofa' -> {\"phrase\": \"\"}"
)
DATE_SCHEMA = {
    "type": "object",
    "properties": {"phrase": {"type": "string"}, "year": {"type": "integer"}, "month": {"type": "integer"},
                   "season": {"type": "string", "enum": ["spring", "summer", "autumn", "winter"]},
                   "relative": {"type": "string", "enum": ["today", "yesterday", "this_week", "last_week", "this_month", "last_month",
                                                             "this_year", "last_year"]},
                   "ago": {"type": "integer"}, "unit": {"type": "string", "enum": ["day", "week", "month", "year"]},
                   "through": {"type": "boolean"}},
    "required": ["phrase"],
}


def apply_dates(plan: Plan, phrase: str, spec: Any) -> Plan:
    """A dedicated step found a time expression: it becomes the plan's date, and any clause that only repeats those words
    (for example the text 'last month') is dropped, because it was a date, not something written in a photo."""
    if not phrase or spec.is_empty:
        return plan
    from ..search.textnorm import tokens

    words = set(tokens(phrase))
    kept = tuple(c for c in plan.clauses if not (words and set(tokens(c.query)) <= words))
    return dataclasses.replace(plan, date=spec, clauses=kept)

def _asks_for_one_thing(plan: Plan) -> bool:
    """Exactly one thing to look for, no date and no other filters. A place filter alone only restates the place."""
    terms = {c.query.strip().lower() for c in plan.clauses if not c.exclude and c.query.strip()}
    others_empty = dataclasses.replace(plan.filters, near="", radius_km=0).is_empty
    return len(terms) == 1 and plan.date.is_empty and others_empty and not any(c.exclude for c in plan.clauses)


def _merge_groups(best: Any, readings: list[tuple[str, np.ndarray]]) -> list[tuple[str, np.ndarray]]:
    """The best match first, then each reading; a reading that finds exactly the same photos as an earlier one is not repeated."""
    out: list[tuple[str, np.ndarray]] = []
    for label, ids in ([best] if best else []) + readings:
        if not any(len(ids) == len(o) and np.array_equal(np.sort(ids), np.sort(o)) for _, o in out):
            out.append((label, ids))
    return out


MAX_REVISIONS = 2  # how many times the agent may look at an empty result and try a different plan


class AgentService:
    def __init__(
        self,
        planner: Planner,
        executor_factory: Callable[[], Executor],
        known_people: Callable[[], list[str]],
        today: Callable[[], date] = date.today,
        library_facts: Callable[[str], str] | None = None,
        answerer: Callable[[str, np.ndarray | None], str] | None = None,
        chatter: Callable[[str, list[tuple[str, str]]], str] | None = None,
        chat_stream: Callable[[str, list[tuple[str, str]]], Any] | None = None,
        router: Callable[[str, bool], str] | None = None,
        fast_search: bool = True,
        rescue: bool = True,
        date_step: Callable[[str], tuple[str, Any]] | None = None,
        reviser: Callable[[str, Plan, str], Plan | None] | None = None,
    ) -> None:
        self._reviser = reviser
        self._date_step = date_step
        self._rescue = rescue
        self._fast_search = fast_search
        self._router = router
        self._chatter = chatter
        self._chat_stream = chat_stream
        self._library_facts = library_facts
        self._answerer = answerer
        self._planner = planner
        self._executor_factory = executor_factory
        self._known_people = known_people
        self._today = today

    def _chat_reply(self, request: str, history: list[tuple[str, str]] | None, base: dict[str, Any], message: str) -> AgentReply:
        fallback = message or "Ask me to find photos by content, text, people, places or dates."
        if self._chat_stream is not None:
            return AgentReply("chat", "", stream=self._chat_stream(request, list(history or [])), **base)
        if self._chatter is None:
            return AgentReply("chat", fallback, **base)
        try:
            return AgentReply("chat", self._chatter(request, list(history or [])) or fallback, **base)
        except LLMError as exc:
            return AgentReply("error", str(exc), **base)

    def ask(
        self, request: str, previous_ids: np.ndarray | None = None, history: list[tuple[str, str]] | None = None
    ) -> AgentReply:
        if not request.strip():
            return AgentReply("clarify", "What would you like to find?")
        timings: dict[str, float] = {}
        route = "photos"
        if self._router is not None:  # a tiny, fast question first: simple search, photo question, or just conversation?
            started = time.perf_counter()
            try:
                route = self._router(request, previous_ids is not None)
            except LLMError as exc:
                return AgentReply("error", str(exc))
            timings["route"] = round(time.perf_counter() - started, 2)
            if route == "chat":
                return self._chat_reply(request, history, {"timings": timings}, "")
        simple = (route == "simple" and self._fast_search and previous_ids is None
                  and 0 < len(request.split()) <= MAX_SIMPLE_WORDS)
        if simple:  # one visual subject: skip the AI plan (about 6 s) and search directly
            subject = request.strip().strip(".!?,;:").lower()
            planned = PlanResult(plan=Plan(intent="find", clauses=(Clause(engines=("visual",), query=subject, exclude=False),)))
        else:
            started = time.perf_counter()
            ctx = PlannerContext(
                today=self._today(),
                known_people=tuple(self._known_people()),
                previous_count=None if previous_ids is None else len(previous_ids),
                library=self._library_facts(request) if self._library_facts else "",
            )
            timings["context"] = round(time.perf_counter() - started, 2)
            started = time.perf_counter()
            try:
                planned = self._planner.plan(request, ctx)
            except (LLMError, PlanningError) as exc:
                return AgentReply("error", str(exc))
            timings["plan"] = round(time.perf_counter() - started, 2)
        return self.run_plan(request, planned.plan, previous_ids, history, planned.warnings, timings)

    def run_plan(
        self,
        request: str,
        plan: Plan,
        previous_ids: np.ndarray | None = None,
        history: list[tuple[str, str]] | None = None,
        warnings: list[str] | None = None,
        timings: dict[str, float] | None = None,
    ) -> AgentReply:
        """Carry out a plan (from the planner or from a tool call) and write the reply. Shared by every kind of agent."""
        timings = {} if timings is None else timings
        warnings = [] if warnings is None else warnings
        if self._date_step is not None and plan.intent in ("find", "count", "export"):  # authoritative: the planner invents dates
            started = time.perf_counter()
            try:  # a small, focused step: is there a time expression the plan missed (or turned into words)?
                phrase, spec = self._date_step(request)
                plan = apply_dates(plan, phrase, spec)
            except LLMError:
                pass  # an extra check must never stop a search
            timings["dates"] = round(time.perf_counter() - started, 2)
        if plan.intent == "count" and not plan.has_constraints and previous_ids is None:
            plan = dataclasses.replace(plan, all_photos=True)  # "how many photos do I have?" means all of them
        base: dict[str, Any] = {"plan": plan, "warnings": warnings, "timings": timings}

        if plan.intent == "chat":
            return self._chat_reply(request, history, base, plan.message)
        if plan.intent == "question":
            if self._answerer is None:
                return AgentReply("chat", "I can't look that up here yet.", **base)
            try:
                return AgentReply("chat", self._answerer(request, previous_ids), **base)
            except LLMError as exc:
                return AgentReply("error", str(exc), **base)
        if plan.intent == "clarify" or not plan.has_constraints:
            return AgentReply(
                "clarify", plan.message or "What should I look for - a subject, text, person, place or date?", **base
            )

        try:
            executor = self._executor_factory()
            started = time.perf_counter()
            outcome = executor.run(plan, previous_ids)
            timings["search"] = round(time.perf_counter() - started, 2)
            if (
                self._rescue
                and len(outcome.ids) == 0
                and plan.intent in ("find", "count", "export")
                and plan.scope == "library"
                and _only_plain_clauses(plan)
                and any(r.matched == 0 for r in outcome.reports)
            ):
                rescued = executor.rescue(request)
                if len(rescued):
                    outcome.ids = rescued
                    outcome.notes.append(
                        "The AI's plan found nothing, so I searched your library for the words you typed. "
                        "These are the closest matches, so double-check them."
                    )
            tried: list[str] = []
            while (
                self._reviser is not None
                and len(outcome.ids) == 0
                and plan.intent in ("find", "count", "export")
                and len(tried) < MAX_REVISIONS
            ):
                # Nothing found: look at WHY, then let the model try a different plan (fewer words, other engine, wider place).
                feedback = f"{explain_empty(outcome.reports)} Search scope was '{plan.scope}'."
                started = time.perf_counter()
                try:
                    revised = self._reviser(request, plan, feedback)
                except LLMError:
                    break
                timings[f"retry{len(tried) + 1}"] = round(time.perf_counter() - started, 2)
                if revised is None or not revised.has_constraints or revised == plan:
                    break
                tried.append(describe_conditions(plan, outcome.date_range))
                plan = revised
                outcome = executor.run(plan, previous_ids if plan.scope == "previous" else None)
                base["plan"] = plan
            if tried and len(outcome.ids):
                outcome.notes.append("My first search found nothing (" + "; ".join(tried) + "), so I tried again with a different approach.")
        except Exception as exc:
            log.exception("plan execution failed")
            return AgentReply("error", f"Something went wrong while searching: {exc}", **base)

        groups: list[tuple[str, np.ndarray]] = []
        lead = ""
        if plan.intent in ("find", "count") and hasattr(executor, "readings"):
            try:
                readings = executor.readings(plan)
                if readings and _asks_for_one_thing(plan):
                    # One thing was asked for: the most reliable way it can be found leads (place and GPS before folders, people, written
                    # text and finally what the picture looks like), instead of a mixed search that silently narrows it to a few photos.
                    lead, outcome.ids = readings[0][0], readings[0][1]
                    groups = _merge_groups(None, readings)
                else:
                    groups = _merge_groups(len(outcome.ids) and ("Best match", outcome.ids), readings)
            except Exception:  # listing the other readings must never break the answer
                log.exception("listing readings failed")
        if len(outcome.ids) == 0 and groups:
            label, ids = groups[0]
            outcome.ids = ids
            outcome.notes.append(f"No exact match. Showing: {label}.")
        common = {
            **base,
            "groups": groups,
            "ids": outcome.ids,
            "reports": outcome.reports,
            "notes": outcome.notes,
            "date_range": outcome.date_range,
        }
        conditions = lead or describe_conditions(plan, outcome.date_range)
        n = len(outcome.ids)
        if n == 0:
            return AgentReply("results", f"No photos found. {explain_empty(outcome.reports)}", **common)
        if plan.intent == "count":
            return AgentReply("count", f"**{n:,}** photo{'s' if n != 1 else ''} · {conditions}", **common)
        if plan.intent == "export":
            return AgentReply(
                "export",
                f"**{n:,}** photo{'s' if n != 1 else ''} · {conditions}. Ready to copy.",
                folder_name=plan.folder_name,
                **common,
            )
        return AgentReply("results", f"**{n:,}** photo{'s' if n != 1 else ''} · {conditions}", **common)
