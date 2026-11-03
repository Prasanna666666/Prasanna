"""High-level agent API used by the UI and CLI.

``AgentService.ask`` is the one entry point: plan -> execute -> explain.  Every
failure mode is converted into an :class:`AgentReply` (kind ``"error"``) so the
caller never has to catch exceptions to keep the interface alive.
"""

from __future__ import annotations

import logging
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
            return f"**{report.label}** matches no photos on its own."
    for report in reports:
        if report.remaining == 0:
            return f"No photo satisfies all conditions together; the set became empty at **{report.label}**."
    return "No photo satisfies the request."


def _only_plain_clauses(plan: Plan) -> bool:
    """Rescue ignores dates, filters and exclusions, so it only applies when the plan has none."""
    return not any(c.exclude for c in plan.clauses) and plan.date.is_empty and plan.filters.is_empty


CHAT_SYSTEM = (
    "You are Lumo, a friendly assistant inside a private photo app. You can talk about anything: answer questions, explain things, "
    "help with writing, give advice, chat. Be concise and clear, like a thoughtful friend. You run offline on the user's own Mac, so "
    "you cannot browse the web or know today's news. You can also find photos when asked (for example 'show me beach photos'); "
    "mention that only when it is relevant. In this reply you are NOT searching photos, so never claim to have found any."
)


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

_GREETINGS = {"hi", "hello", "hey", "hi there", "hello there", "hey there", "good morning", "good afternoon", "good evening"}
_THANKS = {"thanks", "thank you", "thanks a lot", "thank you so much", "thx", "cheers"}
_BYES = {"bye", "goodbye", "good night", "see you", "see ya"}


def instant_reply(request: str) -> str | None:
    """A ready answer for a plain greeting, thanks or goodbye: no AI call, so it appears at once."""
    text = " ".join("".join(ch if ch.isalnum() or ch.isspace() else " " for ch in request.lower()).split())
    if text in _GREETINGS:
        return "Hi! I'm Lumo. Ask me to find photos, like 'beach photos from last summer', or just chat."
    if text in _THANKS:
        return "You're welcome!"
    if text in _BYES:
        return "See you soon!"
    return None


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
    ) -> None:
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
        quick = instant_reply(request)
        if quick:
            return AgentReply("chat", quick)
        route = "photos"
        if self._router is not None:  # a tiny, fast question first: simple search, photo question, or just conversation?
            try:
                route = self._router(request, previous_ids is not None)
            except LLMError as exc:
                return AgentReply("error", str(exc))
            if route == "chat":
                return self._chat_reply(request, history, {}, "")
        simple = (route == "simple" and self._fast_search and previous_ids is None
                  and 0 < len(request.split()) <= MAX_SIMPLE_WORDS)
        if simple:  # one visual subject: skip the AI plan (about 6 s) and search directly
            subject = request.strip().strip(".!?,;:").lower()
            planned = PlanResult(plan=Plan(intent="find", clauses=(Clause(engines=("visual",), query=subject, exclude=False),)))
        else:
            ctx = PlannerContext(
                today=self._today(),
                known_people=tuple(self._known_people()),
                previous_count=None if previous_ids is None else len(previous_ids),
                library=self._library_facts(request) if self._library_facts else "",
            )
            try:
                planned = self._planner.plan(request, ctx)
            except (LLMError, PlanningError) as exc:
                return AgentReply("error", str(exc))
        plan = planned.plan
        base: dict[str, Any] = {"plan": plan, "warnings": planned.warnings}

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
            outcome = executor.run(plan, previous_ids)
            if (
                len(outcome.ids) == 0
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
        except Exception as exc:
            log.exception("plan execution failed")
            return AgentReply("error", f"Something went wrong while searching: {exc}", **base)

        common = {
            **base,
            "ids": outcome.ids,
            "reports": outcome.reports,
            "notes": outcome.notes,
            "date_range": outcome.date_range,
        }
        conditions = describe_conditions(plan, outcome.date_range)
        n = len(outcome.ids)
        if n == 0:
            return AgentReply("results", f"No photos found. {explain_empty(outcome.reports)}", **common)
        if plan.intent == "count":
            return AgentReply("count", f"**{n:,}** photo{'s' if n != 1 else ''} match: {conditions}.", **common)
        if plan.intent == "export":
            return AgentReply(
                "export",
                f"Found **{n:,}** photo{'s' if n != 1 else ''} matching {conditions}. Ready to copy them.",
                folder_name=plan.folder_name,
                **common,
            )
        return AgentReply("results", f"Found **{n:,}** photo{'s' if n != 1 else ''} matching: {conditions}.", **common)
