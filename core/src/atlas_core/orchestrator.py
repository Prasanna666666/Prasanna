"""The Agent Orchestrator (Stage 6; TARGET_ARCHITECTURE 12): a deterministic task state machine over registered, typed task contracts.

A model may PROPOSE a plan, but this module owns the workflow: it accepts only task types a registered agent supports, checks every task's authority against the registry and the parent task, orders dependent
tasks, runs independent ones in parallel, bounds retries and time, honours cancellation, and refuses to call an incomplete workflow complete.

* **Registry, not self-service.** An agent's role, version, task types, permissions, sensitivity ceiling and tools are frozen configuration; the registry is sealed after it is built, and no executor receives
  a way to change any of it. An agent cannot widen its own authority.
* **Least authority, inherited downward.** A child task can have no more sources, tools or sensitivity than its parent and than its agent's registration. The executor is handed only its own contract and the
  results of the tasks it depends on, nothing else.
* **Honest ends.** `completed` only if every task completed (and every high-impact task was independently verified); otherwise `partially_completed`, `failed`, `cancelled` or `expired`, with each task's
  own state. Retries are bounded and only for failures an executor marks transient; there are no loops and no hidden delegation.
* **Direct path first.** Below a planning-confidence threshold the answer is to take the direct single-model path or ask the owner, never to guess a plan.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

SENSITIVITY = ("low", "medium", "high", "restricted")
TERMINAL = frozenset({"completed", "failed", "cancelled", "expired", "skipped"})
MAX_TASKS = 32
MAX_RETRIES = 2
PLAN_CONFIDENCE_FLOOR = 0.6


class Transient(Exception):
    """An executor's way of saying a failure may succeed on retry (a worker crash, a busy model). Anything else is final."""


class PlanRejected(ValueError):
    """The plan does not fit the registry. Carries a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AgentSpec:
    role: str
    version: str
    tasks: frozenset[str]
    sources: frozenset[str]
    tools: frozenset[str]
    max_sensitivity: str = "medium"
    healthy: bool = True


@dataclass(frozen=True)
class TaskContract:
    task_id: str
    task_type: str
    role: str
    objective: str
    sources: frozenset[str] = frozenset()
    tools: frozenset[str] = frozenset()
    sensitivity: str = "low"
    parent: str | None = None
    depends_on: tuple[str, ...] = ()
    high_impact: bool = False
    seconds: float = 30.0


@dataclass
class TaskResult:
    state: str = "queued"  # queued | running | completed | failed | cancelled | expired | skipped
    output: Any = None
    verified: bool | None = None
    attempts: int = 0
    code: str = ""


@dataclass(frozen=True)
class TaskContext:
    """All an executor receives: its contract and the outputs of its declared dependencies. Not the plan, not other tasks, not the registry."""

    contract: TaskContract
    inputs: Mapping[str, Any]


Executor = Callable[[TaskContext], Any]


@dataclass
class RunReport:
    status: str
    tasks: dict[str, TaskResult] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


class Registry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}
        self._sealed = False

    def register(self, spec: AgentSpec) -> None:
        if self._sealed:
            raise PlanRejected("registry_sealed")  # configuration is closed: nothing at run time can add or change an agent
        if spec.role in self._agents or spec.max_sensitivity not in SENSITIVITY:
            raise ValueError("bad agent")
        self._agents[spec.role] = spec

    def seal(self) -> None:
        self._sealed = True

    def get(self, role: str) -> AgentSpec | None:
        return self._agents.get(role)


def choose_path(confidence: float, direct_ok: bool = True) -> str:
    """`plan` when the planner is confident enough; otherwise the direct single-model path, or ask the owner when there is none. Never a guess."""
    if confidence >= PLAN_CONFIDENCE_FLOOR:
        return "plan"
    return "direct" if direct_ok else "ask_owner"


def _check_task(t: TaskContract, by_id: Mapping[str, TaskContract], registry: Registry) -> None:
    agent = registry.get(t.role)
    if agent is None or not agent.healthy:
        raise PlanRejected("unknown_or_unhealthy_agent")
    if t.task_type not in agent.tasks:
        raise PlanRejected("task_type_not_supported")  # a model can select only among what the registry permits
    if t.sensitivity not in SENSITIVITY or SENSITIVITY.index(t.sensitivity) > SENSITIVITY.index(agent.max_sensitivity):
        raise PlanRejected("sensitivity_above_agent_ceiling")
    if not t.sources <= agent.sources or not t.tools <= agent.tools:
        raise PlanRejected("authority_above_agent_registration")
    if t.parent is not None:
        parent = by_id.get(t.parent)
        if parent is None:
            raise PlanRejected("unknown_parent")
        if not (t.sources <= parent.sources and t.tools <= parent.tools) or SENSITIVITY.index(t.sensitivity) > SENSITIVITY.index(parent.sensitivity):
            raise PlanRejected("child_exceeds_parent")  # a child inherits no more authority than its parent
    if any(d not in by_id or d == t.task_id for d in t.depends_on):
        raise PlanRejected("bad_dependency")


def validate(plan: list[TaskContract], registry: Registry) -> None:
    if not plan or len(plan) > MAX_TASKS:
        raise PlanRejected("plan_size")
    by_id = {t.task_id: t for t in plan}
    if len(by_id) != len(plan):
        raise PlanRejected("duplicate_task")
    for t in plan:
        _check_task(t, by_id, registry)
    seen: set[str] = set()
    pending = list(plan)
    while pending:  # a cycle is a plan that can never run
        ready = [t for t in pending if all(d in seen for d in t.depends_on)]
        if not ready:
            raise PlanRejected("dependency_cycle")
        seen |= {t.task_id for t in ready}
        pending = [t for t in pending if t.task_id not in seen]


@dataclass
class RunOptions:
    verifier: Callable[[TaskContract, Any], bool] | None = None
    cancelled: Callable[[], bool] = lambda: False
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    total_seconds: float = 120.0
    workers: int = 4


class _Run:
    def __init__(self, plan: list[TaskContract], executors: Mapping[str, Executor], options: RunOptions) -> None:
        self.by_id = {t.task_id: t for t in plan}
        self.report = RunReport("completed", {t.task_id: TaskResult() for t in plan})
        self.executors, self.options = executors, options
        self.deadline = options.clock() + timedelta(seconds=options.total_seconds)

    def execute(self, contract: TaskContract) -> None:
        result = self.report.tasks[contract.task_id]
        inputs = {d: self.report.tasks[d].output for d in contract.depends_on}
        while True:
            if self.options.cancelled():
                result.state = "cancelled"
                return
            if self.options.clock() > self.deadline:
                result.state, result.code = "expired", "deadline"
                return
            result.state, result.attempts = "running", result.attempts + 1
            try:
                result.output = self.executors[contract.role](TaskContext(contract, inputs))
            except Transient:
                if result.attempts > MAX_RETRIES:
                    result.state, result.code = "failed", "retries_exhausted"
                    return
                continue
            except Exception:  # noqa: BLE001  (a failure is a code; its text could carry content)
                result.state, result.code = "failed", "executor_failed"
                return
            if contract.high_impact:
                verifier = self.options.verifier
                result.verified = bool(verifier and verifier(contract, result.output))  # no verifier, no verification
            result.state = "completed"
            return

    def _state(self, task_id: str) -> str:
        return self.report.tasks[task_id].state

    def drive(self) -> None:
        remaining = set(self.by_id)
        with ThreadPoolExecutor(max_workers=self.options.workers) as pool:
            while remaining:
                ready = [self.by_id[i] for i in sorted(remaining) if all(self._state(d) == "completed" for d in self.by_id[i].depends_on)]
                blocked = [i for i in sorted(remaining) if any(self._state(d) in TERMINAL - {"completed"} for d in self.by_id[i].depends_on)]
                for i in blocked:
                    self.report.tasks[i].state, self.report.tasks[i].code = "skipped", "dependency_not_completed"
                    remaining.discard(i)
                if not ready and not blocked:
                    break
                remaining -= {t.task_id for t in ready}
                list(pool.map(self.execute, ready))  # independent tasks run together; dependents wait for the next round

    def finish(self) -> RunReport:
        states = [r.state for r in self.report.tasks.values()]
        unverified = [i for i, r in self.report.tasks.items() if self.by_id[i].high_impact and r.state == "completed" and not r.verified]
        if all(s == "completed" for s in states) and not unverified:
            self.report.status = "completed"
        elif "cancelled" in states:
            self.report.status = "cancelled"
        elif "expired" in states:
            self.report.status = "expired"
        elif "completed" in states:
            self.report.status = "partially_completed"
        else:
            self.report.status = "failed"
        if unverified:
            self.report.reasons.append("high_impact_not_verified")
        return self.report


def run(plan: list[TaskContract], registry: Registry, executors: Mapping[str, Executor], options: RunOptions | None = None) -> RunReport:
    validate(plan, registry)
    state = _Run(plan, executors, options or RunOptions())
    state.drive()
    return state.finish()
