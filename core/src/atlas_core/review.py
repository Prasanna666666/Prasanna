"""The owner's review (Stage 6): the orchestrator run on a real, fixed workflow with specialist agents that are plain code, not models.

One task per area (calendar, finance, health), run together, then one task that puts the sections in order. The plan is fixed here, so a model never proposes it; every task's authority comes from the sealed
registry; Finance and Health run only under their own grant (the callables behind them check it and answer `denied` otherwise). Every figure is the one the Core already computed by code; nothing is
rewritten, rounded or estimated here. An area that is off, empty or not offered is reported as such, and the review is `partially_completed` only if a task actually failed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import CoreError
from .finance_calc import MONEY_DOMAIN
from .health_calc import HEALTH_DOMAIN
from .orchestrator import AgentSpec, Registry, RunOptions, TaskContext, TaskContract, run

CALENDAR = "calendar"
HIGHLIGHTS = "highlights"
AREAS = (CALENDAR, MONEY_DOMAIN, HEALTH_DOMAIN, HIGHLIGHTS)


def _registry() -> Registry:
    registry = Registry()
    registry.register(AgentSpec("calendar_agent", "1", frozenset({"check_calendar"}), frozenset(), frozenset(), "medium"))
    registry.register(AgentSpec("finance_agent", "1", frozenset({"summarise_finance"}), frozenset({MONEY_DOMAIN}), frozenset(), "restricted"))
    registry.register(AgentSpec("health_agent", "1", frozenset({"summarise_health"}), frozenset({HEALTH_DOMAIN}), frozenset(), "restricted"))
    registry.register(
        AgentSpec("highlights_agent", "1", frozenset({"summarise_sources"}), frozenset(), frozenset(), "high")
    )  # model-backed: it only STARTS a task; the answer is the verified, cited one from the normal pipeline
    registry.register(AgentSpec("review_writer", "1", frozenset({"compose"}), frozenset(), frozenset(), "restricted"))
    registry.seal()
    return registry


def _plan() -> list[TaskContract]:
    return [
        TaskContract(CALENDAR, "check_calendar", "calendar_agent", "Find overlapping events", sensitivity="medium"),
        TaskContract(MONEY_DOMAIN, "summarise_finance", "finance_agent", "Summarise spending", sources=frozenset({MONEY_DOMAIN}), sensitivity="restricted"),
        TaskContract(HEALTH_DOMAIN, "summarise_health", "health_agent", "Summarise readings", sources=frozenset({HEALTH_DOMAIN}), sensitivity="restricted"),
        TaskContract(HIGHLIGHTS, "summarise_sources", "highlights_agent", "Start a verified summary of the owner's sources", sensitivity="high"),
        TaskContract(
            "compose",
            "compose",
            "review_writer",
            "Order the sections",
            sensitivity="restricted",
            depends_on=(CALENDAR, MONEY_DOMAIN, HEALTH_DOMAIN, HIGHLIGHTS),
        ),
    ]


def _offered(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return call()
    except CoreError as error:
        if error.code == "not_found":
            return {"state": "unavailable"}  # this Core has no such source
        raise


def _calendar(attention: Callable[[], dict[str, Any]] | None) -> dict[str, Any]:
    if attention is None:
        return {"area": CALENDAR, "state": "unavailable", "summary": "Your own calendar is not available here."}
    items = attention().get("items", [])
    if not items:
        return {"area": CALENDAR, "state": "ready", "summary": "No events overlap."}
    word = "event pair overlaps" if len(items) == 1 else "event pairs overlap"
    return {"area": CALENDAR, "state": "ready", "summary": f"{len(items)} {word}: " + "; ".join(str(i["title"]) for i in items[:3]) + "."}


def _finance(summary: dict[str, Any]) -> dict[str, Any]:
    state = summary["state"]
    if state != "ready":
        return {"area": MONEY_DOMAIN, "state": state, "summary": _NOT_READY[state]}
    latest = summary["latest"]
    return {
        "area": MONEY_DOMAIN,
        "state": "ready",
        "summary": f"Spent {latest['total']} {summary['currency']} in {latest['month']}, added up by code from {summary['transaction_count']} transactions.",
    }


def _health(summary: dict[str, Any]) -> dict[str, Any]:
    state = summary["state"]
    if state != "ready":
        return {"area": HEALTH_DOMAIN, "state": state, "summary": _NOT_READY[state]}
    count = len(summary["measures"])
    return {
        "area": HEALTH_DOMAIN,
        "state": "ready",
        "summary": f"{summary['reading_count']} readings across {count} {'measure' if count == 1 else 'measures'}, summarised by code.",
    }


_NOT_READY = {
    "denied": "This area is off. Turn it on in Settings to include it.",
    "empty": "Nothing has been added here yet.",
    "unavailable": "This area is not available here.",
}


def _highlights(started: dict[str, Any]) -> dict[str, Any]:
    state = started["state"]
    if state != "ready":
        return {"area": HIGHLIGHTS, "state": state, "summary": _NOT_READY.get(state, _NOT_READY["unavailable"])}
    return {
        "area": HIGHLIGHTS,
        "state": "ready",
        "summary": "A summary of your enabled sources is being written. It is checked against its sources, and every claim is cited.",
        "task_id": started["task_id"],
    }


def run_review(
    finance: Callable[[], dict[str, Any]],
    health: Callable[[], dict[str, Any]],
    attention: Callable[[], dict[str, Any]] | None,
    highlights: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the review and return its honest outcome: the workflow status, each task's own state, and the sections."""
    sections: dict[str, dict[str, Any]] = {}
    executors = {
        "calendar_agent": lambda _c: sections.setdefault("calendar", _calendar(attention)),
        "finance_agent": lambda _c: sections.setdefault(MONEY_DOMAIN, _finance(_offered(finance))),
        "health_agent": lambda _c: sections.setdefault(HEALTH_DOMAIN, _health(_offered(health))),
        "highlights_agent": lambda _c: sections.setdefault(HIGHLIGHTS, _highlights(highlights() if highlights else {"state": "unavailable"})),
        "review_writer": lambda ctx: _compose(ctx, sections),
    }
    report = run(_plan(), _registry(), executors, RunOptions())
    return {
        "status": report.status,
        "tasks": [{"task": name, "state": result.state} for name, result in report.tasks.items()],
        "sections": [sections[a] for a in AREAS if a in sections],
        "computed_by_code": True,
    }


def _compose(_ctx: TaskContext, sections: dict[str, dict[str, Any]]) -> int:
    return len(sections)
