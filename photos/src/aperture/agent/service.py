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
from .planner import Planner, PlannerContext, PlanningError, PlanResult
from .progress import say
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
    timings: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)  # seconds spent in each step
    groups: list[tuple[str, np.ndarray]] = field(
        default_factory=list, repr=False, compare=False
    )  # every reading of the query, best first
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
    "You are the Photos assistant in a private photo app on the user's Mac. Chat naturally and warmly, in one or two short sentences of "
    "plain text, without emojis or lists. If the user is just being social, reply kindly and invite them to describe photos to find. "
    "For a general question, answer briefly and correctly. You cannot browse the web. You are not searching photos in this reply, "
    "so never claim to have found any.\n"
    "If the user questions or corrects the earlier results, answer from the notes in the conversation (what was searched, how many, which "
    "readings) in plain words: say what you searched, admit it if it looks wrong, and suggest how to narrow it. Never claim you searched again. "
    "When asked whether you found everything, use the location coverage in the notes: say how many photos have no location and so cannot be "
    "found by place, and offer to look at photos from the same days instead.\n"
    "Examples:\n"
    "User: Hello\nAssistant: Hi! What would you like to find in your photos today?\n"
    "User: How are you?\nAssistant: Doing well, thanks for asking! Shall I look for some photos?\n"
    "User: What is a RAW file?\nAssistant: A RAW file is the unprocessed data straight from a camera sensor, so it holds more detail to edit than a JPEG."
)
CHAT_MAX_TOKENS = 160  # short answers: it is a photo app, and short answers are also fast

ROUTER_SYSTEM = (
    'You route messages in a private photo app. Reply with JSON: {"route": "simple"}, {"route": "photos"}, {"route": "about"} or {"route": "chat"}.\n'
    "simple = ONE subject to look for in the pictures themselves (an object, animal, food, scene or activity) and nothing else: no "
    "person's name, place, date or year, count, filter, 'not' or 'without', text written in a picture, and no earlier results. "
    "At most 4 words.\n"
    "photos = any other message about the user's photos or files or library: find, show, count, filter, copy or organize them, "
    "refine earlier results, or ask about them (how many, from which year, which people, places, indexing). Words like photos, pics, "
    "pictures, images, shots, selfies, albums, years and dates about their library mean photos. When in doubt, choose photos.\n"
    "about = the user comments on, questions or complains about the EARLIER ANSWER or the app itself, without asking to find anything new: "
    "'why are these from Iceland?', 'that is wrong', 'what did you search for?', 'why only 8?', 'how did you decide that?'. "
    "If the user corrects AND names what they want ('no, I meant Japan'), that is photos.\n"
    "chat = everything else: greetings, thanks, small talk, general knowledge, explanations, advice, writing help, questions about you.\n"
    "Examples: 'mountains' -> simple; 'birthday cake' -> simple; 'a cup of coffee' -> simple; 'sailing boats' -> simple; "
    "'photos of Anna at the beach' -> photos; 'sunset photos from 2023' -> photos; 'beach photos without people' -> photos; "
    "'find the invoice that mentions Acme' -> photos; 'how many pics from 2019' -> photos; 'only the ones from March' -> photos; "
    "'who is in my photos most' -> photos; 'why are these Iceland photos?' -> about; 'that is wrong' -> about; 'what did you search for?' -> about; "
    "'no, I meant the ones from Japan' -> photos; 'what is RAW?' -> chat; 'thanks!' -> chat; 'tell me a joke' -> chat; 'what is 12 times 12' -> chat."
)
ROUTER_SCHEMA = {
    "type": "object",
    "properties": {"route": {"type": "string", "enum": ["simple", "photos", "about", "chat"]}},
    "required": ["route"],
}
MAX_SIMPLE_WORDS = 4

DATE_SYSTEM = (
    "Find the time expression in the user's message. phrase = the exact words that express a time or period (for example 'last month', "
    "'in 2021', 'this summer', 'yesterday', 'March'), or an empty string if there is none. Fill year (like 2021), month (1-12), season or "
    "relative ONLY from that phrase and leave the other fields out. Never compute dates.\n"
    "For 'N units ago' style phrases set ago and unit, and also span: 'period' when the user means that ONE period ('2 months back', "
    "'3 weeks ago'), or 'until_now' when the user means the whole stretch from then until today ('the last 3 months', 'the past 2 weeks', "
    "'in the last 10 days', 'recent months').\n"
    "Examples:\n"
    '\'pics from last month\' -> {"phrase": "last month", "relative": "last_month"}\n'
    '\'what I shot in August 2019\' -> {"phrase": "August 2019", "year": 2019, "month": 8}\n'
    '\'skiing trip winter 2023\' -> {"phrase": "winter 2023", "year": 2023, "season": "winter"}\n'
    '\'pics from 2 months back\' -> {"phrase": "2 months back", "ago": 2, "unit": "month", "span": "period"}\n'
    '\'photos from the last 3 weeks\' -> {"phrase": "the last 3 weeks", "ago": 3, "unit": "week", "span": "until_now"}\n'
    '\'pictures from the last 3 months\' -> {"phrase": "the last 3 months", "ago": 3, "unit": "month", "span": "until_now"}\n'
    '\'what did I shoot in the past 10 days\' -> {"phrase": "the past 10 days", "ago": 10, "unit": "day", "span": "until_now"}\n'
    '\'cats on the sofa\' -> {"phrase": ""}'
)
DATE_SCHEMA = {
    "type": "object",
    "properties": {
        "phrase": {"type": "string"},
        "year": {"type": "integer"},
        "month": {"type": "integer"},
        "season": {"type": "string", "enum": ["spring", "summer", "autumn", "winter"]},
        "relative": {
            "type": "string",
            "enum": ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_year", "last_year"],
        },
        "ago": {"type": "integer"},
        "unit": {"type": "string", "enum": ["day", "week", "month", "year"]},
        "through": {"type": "boolean"},
        "span": {"type": "string", "enum": ["period", "until_now"]},
    },
    "required": ["phrase"],
}


TIME_WORDS = frozenset(
    [
        "ago",
        "back",
        "last",
        "past",
        "previous",
        "this",
        "next",
        "since",
        "before",
        "after",
        "during",
        "until",
        "between",
        "earlier",
        "later",
        "recent",
        "recently",
        "lately",
        "today",
        "yesterday",
        "tonight",
        "morning",
        "afternoon",
        "evening",
        "night",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "day",
        "days",
        "weekend",
        "weekday",
        "weekdays",
        "season",
        "spring",
        "summer",
        "autumn",
        "fall",
        "winter",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "christmas",
        "easter",
        "diwali",
        "holiday",
        "holidays",
        "birthday",
    ]
)


def mentions_time(request: str) -> bool:
    """Does the message contain anything that could be a time? If not, the date step (a model call) is skipped."""
    import re

    words = re.findall(r"[a-z0-9]+", request.lower())
    return any(w in TIME_WORDS or (w.isdigit() and len(w) in (2, 4)) for w in words)


def apply_dates(plan: Plan, phrase: str, spec: Any) -> Plan:
    """A dedicated step found a time expression: it becomes the plan's date, and any clause that only repeats those words
    (for example the text 'last month') is dropped, because it was a date, not something written in a photo."""
    if not phrase or spec.is_empty:
        return plan
    from ..search.textnorm import tokens

    words = set(tokens(phrase))
    kept = tuple(c for c in plan.clauses if not (words and set(tokens(c.query)) <= words))
    return dataclasses.replace(plan, date=spec, clauses=kept)


def show_previous(previous_ids: np.ndarray, timings: dict[str, Any] | None = None) -> AgentReply:
    """'Show them': put the photos that are already on screen back, unchanged."""
    n = len(previous_ids)
    return AgentReply(
        "results", f"**{n:,}** photo{'s' if n != 1 else ''} · the same photos", ids=previous_ids, timings=timings or {}
    )


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
        timings: dict[str, Any] = {}
        route = "photos"
        if self._router is not None:  # a tiny, fast question first: simple search, photo question, or just conversation?
            started = time.perf_counter()
            try:
                route = self._router(request, previous_ids is not None)
            except LLMError as exc:
                return AgentReply("error", str(exc))
            timings["route"] = round(time.perf_counter() - started, 2)
            if route in ("chat", "about"):
                return self._chat_reply(request, history, {"timings": timings}, "")
        simple = route == "simple" and self._fast_search and previous_ids is None and 0 < len(request.split()) <= MAX_SIMPLE_WORDS
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
        timings: dict[str, Any] | None = None,
    ) -> AgentReply:
        """Carry out a plan (from the planner or from a tool call) and write the reply. Shared by every kind of agent."""
        timings = {} if timings is None else timings
        warnings = [] if warnings is None else warnings
        plan = self._with_dates(request, plan, timings)
        if plan.intent == "count" and not plan.has_constraints and previous_ids is None:
            plan = dataclasses.replace(plan, all_photos=True)  # "how many photos do I have?" means all of them
        base: dict[str, Any] = {"plan": plan, "warnings": warnings, "timings": timings}

        early = self._reply_without_search(request, plan, previous_ids, history, base, timings)
        if early is not None:
            return early
        try:
            executor = self._executor_factory()
            plan, outcome = self._search(executor, request, plan, previous_ids, timings)
            base["plan"] = plan
        except Exception as exc:
            log.exception("plan execution failed")
            return AgentReply("error", f"Something went wrong while searching: {exc}", **base)

        say("Checking the results")
        outcome, hard_ids = self._relax_if_empty(executor, plan, previous_ids, outcome)
        groups, lead, exploration = self._arrange(executor, plan, outcome)
        groups = self._enforce(plan, outcome, groups, exploration, hard_ids)
        return self._final_reply(plan, outcome, groups, lead, base)

    def _with_dates(self, request: str, plan: Plan, timings: dict[str, Any]) -> Plan:
        """The date step is authoritative: the planner invents dates."""
        if self._date_step is None or plan.intent not in ("find", "count", "export") or not mentions_time(request):
            return plan
        started = time.perf_counter()
        try:  # a small, focused step: is there a time expression the plan missed (or turned into words)?
            phrase, spec = self._date_step(request)
            plan = apply_dates(plan, phrase, spec)
        except LLMError:
            pass  # an extra check must never stop a search
        timings["dates"] = round(time.perf_counter() - started, 2)
        return plan

    def _reply_without_search(
        self,
        request: str,
        plan: Plan,
        previous_ids: np.ndarray | None,
        history: Any,
        base: dict[str, Any],
        timings: dict[str, Any],
    ) -> AgentReply | None:
        """Small talk, questions about the library, 'show them again' and unclear requests: answered without searching."""
        if plan.intent == "chat":
            return self._chat_reply(request, history, base, plan.message)
        if plan.intent == "question":
            if self._answerer is None:
                return AgentReply("chat", "I can't look that up here yet.", **base)
            try:
                return AgentReply("chat", self._answerer(request, previous_ids), **base)
            except LLMError as exc:
                return AgentReply("error", str(exc), **base)
        if not plan.has_constraints and plan.scope == "previous" and previous_ids is not None and len(previous_ids):
            return show_previous(previous_ids, timings)
        if plan.intent == "clarify" or not plan.has_constraints:
            return AgentReply(
                "clarify", plan.message or "What should I look for - a subject, text, person, place or date?", **base
            )
        return None

    def _search(
        self, executor: Any, request: str, plan: Plan, previous_ids: np.ndarray | None, timings: dict[str, Any]
    ) -> tuple[Plan, Any]:
        """Run the plan; if it finds nothing, rescue with the typed words, then let the model revise the plan a few times."""
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
                    "The AI's plan found nothing, so I searched your library for the words you typed. These are the closest matches, so double-check them."
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
        if tried and len(outcome.ids):
            outcome.notes.append(
                "My first search found nothing (" + "; ".join(tried) + "), so I tried again with a different approach."
            )
        return plan, outcome

    def _relax_if_empty(self, executor: Any, plan: Plan, previous_ids: np.ndarray | None, outcome: Any) -> tuple[Any, Any]:
        """Nothing found for a find: keep the place, date or person and relax only the look. Returns the outcome and the photos that match the rest."""
        if len(outcome.ids) != 0 or plan.intent != "find" or not hasattr(executor, "run_relaxed"):
            return outcome, None
        relaxed = executor.run_relaxed(plan, previous_ids)
        if not len(relaxed.ids):
            return outcome, None
        what = " and ".join(c.query for c in plan.clauses if not c.exclude and tuple(c.engines) == ("visual",))
        outcome.ids, outcome.notes = (
            relaxed.ids,
            [
                *outcome.notes,
                f"No photo clearly shows {what}. These are the closest of the {len(relaxed.hard):,} photos that match the rest.",
            ],
        )
        return outcome, relaxed.hard

    def _arrange(self, executor: Any, plan: Plan, outcome: Any) -> tuple[list[tuple[str, np.ndarray]], str, Any]:
        """Group the photos by the kind of evidence that found them (a place, a folder, a person, written text, how it looks). Returns (groups, lead label, exploration)."""
        groups: list[tuple[str, np.ndarray]] = []
        lead = ""
        exploration = None
        if plan.intent not in ("find", "count") or not hasattr(executor, "readings"):
            return groups, lead, exploration
        try:
            exploration = executor.explore(plan) if hasattr(executor, "explore") else None
            readings = exploration.readings if exploration is not None else executor.readings(plan)
            together = exploration.together() if exploration is not None else None
            if together is not None and len(together):
                # Several conditions: each is judged by its OWN best evidence (a folder, a place, GPS, a trusted label ...) and the answer is
                # where all of them hold, not whatever the model's guessed search method happened to give.
                terms = exploration.terms if exploration is not None else []
                lead, outcome.ids = " and ".join(terms) if terms else "all of it", together
                groups = [(lead, together)]  # one clear answer, no pile of other categories
            elif readings and _asks_for_one_thing(plan):
                # One thing was asked for: the most reliable way it can be found leads (place and GPS before folders, people, written
                # text and finally what the picture looks like), instead of a mixed search that silently narrows it to a few photos.
                lead, outcome.ids = readings[0][0], readings[0][1]
                groups = _merge_groups(None, readings)
            else:
                groups = _merge_groups(len(outcome.ids) and ("Best match", outcome.ids), readings)
        except Exception:  # listing the other readings must never break the answer
            log.exception("listing readings failed")
        return groups, lead, exploration

    def _enforce(
        self, plan: Plan, outcome: Any, groups: list[tuple[str, np.ndarray]], exploration: Any, hard_ids: Any
    ) -> list[tuple[str, np.ndarray]]:
        """What was asked for is a requirement, not a hint: a named place must hold for every photo, and a compound request keeps its exact conditions."""
        if exploration is not None:
            for clause in plan.clauses:
                term = clause.query.strip()
                if clause.exclude or "place" not in clause.engines or "visual" in clause.engines or term not in exploration.terms:
                    continue
                inside = exploration.terms[term]
                if len(inside) == 0:
                    continue  # nothing is known about that place: do not wipe the answer
                outcome.ids = outcome.ids[np.isin(outcome.ids, inside)]
                groups = [(label, ids[np.isin(ids, inside)]) for label, ids in groups]
                groups = [(label, ids) for label, ids in groups if len(ids)]
        if hard_ids is not None:  # a compound request: every tab must still respect its exact requirements
            groups = [(label, np.intersect1d(ids, hard_ids)) for label, ids in groups]
            groups = [(label, ids) for label, ids in groups if len(ids)]
        if (
            len(outcome.ids) == 0 and groups and _asks_for_one_thing(plan)
        ):  # never for a compound request: that would drop a place or a date
            label, ids = groups[0]
            outcome.ids = ids
            outcome.notes.append(f"No exact match. Showing: {label}.")
        return groups

    def _final_reply(
        self, plan: Plan, outcome: Any, groups: list[tuple[str, np.ndarray]], lead: str, base: dict[str, Any]
    ) -> AgentReply:
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
        photos = f"**{n:,}** photo{'s' if n != 1 else ''} · {conditions}"
        if n == 0:
            return AgentReply("results", f"No photos found. {explain_empty(outcome.reports)}", **common)
        if plan.intent == "count":
            return AgentReply("count", photos, **common)
        if plan.intent == "export":
            return AgentReply("export", f"{photos}. Ready to copy.", folder_name=plan.folder_name, **common)
        return AgentReply("results", photos, **common)
