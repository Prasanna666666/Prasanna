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
from .planner import Planner, PlannerContext, PlanningError
from .schema import Plan

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


class Agent(Protocol):
    def ask(self, request: str, previous_ids: np.ndarray | None = None) -> AgentReply: ...


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


class AgentService:
    def __init__(
        self,
        planner: Planner,
        executor_factory: Callable[[], Executor],
        known_people: Callable[[], list[str]],
        today: Callable[[], date] = date.today,
        library_facts: Callable[[str], str] | None = None,
        answerer: Callable[[str, np.ndarray | None], str] | None = None,
    ) -> None:
        self._library_facts = library_facts
        self._answerer = answerer
        self._planner = planner
        self._executor_factory = executor_factory
        self._known_people = known_people
        self._today = today

    def ask(self, request: str, previous_ids: np.ndarray | None = None) -> AgentReply:
        if not request.strip():
            return AgentReply("clarify", "What would you like to find?")
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
            return AgentReply("chat", plan.message or "Ask me to find photos by content, text, people, places or dates.", **base)
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
