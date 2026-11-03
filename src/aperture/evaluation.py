"""Accuracy measurement: does Aperture understand requests and return the right photos?

Two harnesses, both usable from the CLI (``aperture eval-plans`` / ``aperture eval``):

* **Plan accuracy** - a built-in set of varied requests with the expected
  structured plan.  It measures the local LLM + prompt, needs no photos, and
  shows the model's real accuracy on this machine.
* **Retrieval accuracy** - the user's own golden set (request -> files that are
  truly relevant).  Reports precision/recall and can sweep the visual
  strictness presets to pick the best one.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

from .agent.planner import PlannerContext, PlanResult
from .agent.schema import Plan
from .search.textnorm import tokens

TARGET = 0.90


class PlanProducer(Protocol):
    def plan(self, request: str, ctx: PlannerContext) -> PlanResult: ...


# --------------------------------------------------------------------------
# Plan accuracy
# --------------------------------------------------------------------------
def load_plan_cases() -> list[dict[str, Any]]:
    data = resources.files("aperture").joinpath("eval_data/plan_cases.json").read_text(encoding="utf-8")
    return list(json.loads(data))


def _clause_ok(expected: dict[str, Any], plan: Plan) -> bool:
    want = set(tokens(expected["query"]))
    for clause in plan.clauses:
        if (
            clause.exclude == bool(expected["exclude"])
            and set(clause.engines) & set(expected["engines"])
            and want <= set(tokens(clause.query))
        ):
            return True
    return False


def plan_mismatches(plan: Plan, expect: dict[str, Any]) -> list[str]:
    """Why ``plan`` differs from the expectation (empty list = correct).

    Extra clauses count as errors: inventing constraints is how false positives start."""
    problems: list[str] = []
    if plan.intent != expect["intent"]:
        problems.append(f"intent {plan.intent!r} != {expect['intent']!r}")
    if expect["intent"] in ("chat", "clarify"):
        return problems
    if plan.scope != expect["scope"]:
        problems.append(f"scope {plan.scope!r} != {expect['scope']!r}")
    if bool(plan.all_photos) != bool(expect["all_photos"]):
        problems.append("all_photos differs")
    for clause in expect["clauses"]:
        if not _clause_ok(clause, plan):
            problems.append(f"missing clause {clause['engines']}:{clause['query']}{' (NOT)' if clause['exclude'] else ''}")
    if len(plan.clauses) > len(expect["clauses"]):
        problems.append(f"{len(plan.clauses) - len(expect['clauses'])} invented clause(s)")
    if len(expect["clauses"]) > 1 and plan.match != expect["match"]:
        problems.append(f"match {plan.match!r} != {expect['match']!r}")
    for key, want in expect["date"].items():
        if getattr(plan.date, key) != want:
            problems.append(f"date.{key} {getattr(plan.date, key)!r} != {want!r}")
    if not expect["date"] and not plan.date.is_empty:
        problems.append("invented a date")
    for key, want in expect["filters"].items():
        got = getattr(plan.filters, key)
        if (key == "near" and str(got).lower() != str(want).lower()) or (key != "near" and got != want):
            problems.append(f"filters.{key} {got!r} != {want!r}")
    if expect["filters"]:
        extra = {
            k
            for k in ("time_of_day", "day_type", "orientation", "quality", "has_gps", "kind")
            if getattr(plan.filters, k) != "none" and k not in expect["filters"]
        }
        if extra:
            problems.append(f"invented filters {sorted(extra)}")
    elif not plan.filters.is_empty:
        problems.append("invented filters")
    if expect["folder_name"] and not plan.folder_name:
        problems.append("no folder name")
    return problems


@dataclass
class PlanEval:
    total: int = 0
    correct: int = 0
    failures: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def evaluate_plans(
    planner: PlanProducer,
    cases: list[dict[str, Any]] | None = None,
    today: date | None = None,
    on_case: Callable[[int, int], None] | None = None,
) -> PlanEval:
    result = PlanEval()
    cases = cases if cases is not None else load_plan_cases()
    for n, case in enumerate(cases, start=1):
        ctx = PlannerContext(
            today=today or date.today(), known_people=tuple(case["people"]), previous_count=5 if case["previous"] else None
        )
        result.total += 1
        try:
            plan = planner.plan(case["request"], ctx).plan
            problems = plan_mismatches(plan, case["expect"])
        except Exception as exc:
            problems = [f"{type(exc).__name__}: {exc}"]
        if problems:
            result.failures.append((case["request"], problems))
        else:
            result.correct += 1
        if on_case:
            on_case(n, len(cases))
    return result


# --------------------------------------------------------------------------
# Retrieval accuracy against the user's golden set
# --------------------------------------------------------------------------
@dataclass
class CaseScore:
    request: str
    returned: int
    relevant: int
    true_positive: int

    @property
    def precision(self) -> float:
        return self.true_positive / self.returned if self.returned else (1.0 if self.relevant == 0 else 0.0)

    @property
    def recall(self) -> float:
        return self.true_positive / self.relevant if self.relevant else 1.0


@dataclass
class RetrievalEval:
    cases: list[CaseScore] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return sum(c.precision for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def recall(self) -> float:
        return sum(c.recall for c in self.cases) / len(self.cases) if self.cases else 0.0


GOLDEN_TEMPLATE = {
    "_help": "relevant = files (relative to the photo folder) that truly match the request. Use [] when nothing should match. 20+ varied requests give a meaningful score.",
    "cases": [
        {"request": "photos of the beach", "relevant": ["Holidays/Goa/IMG_1.jpg", "Holidays/Goa/IMG_2.jpg"]},
        {"request": "pictures of a unicorn", "relevant": []},
    ],
}


def evaluate_retrieval(ask: Callable[[str], list[str]], golden: dict[str, Any]) -> RetrievalEval:
    """``ask`` returns relative paths for a request; ``golden`` is the user's file."""
    result = RetrievalEval()
    for case in golden.get("cases", []):
        want = {str(Path(p)) for p in case.get("relevant", [])}
        got = {str(Path(p)) for p in ask(str(case["request"]))}
        result.cases.append(CaseScore(str(case["request"]), len(got), len(want), len(want & got)))
    return result


def evaluate_routes(router, cases: list[dict]) -> tuple[int, list[str]]:
    """How many messages the router sends to the right place ('photos' = about the library, 'chat' = conversation)."""
    correct, wrong = 0, []
    for case in cases:
        got = router(case["message"], bool(case.get("previous")))
        if got == case["expect"]:
            correct += 1
        else:
            wrong.append(f"{case['message']!r}: sent to {got}, expected {case['expect']}")
    return correct, wrong
