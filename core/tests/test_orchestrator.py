"""Stage 6: the Agent Orchestrator is a deterministic state machine over a sealed registry: least authority inherited downward, bounded retries, honest ends, direct path first."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from atlas_core.orchestrator import (
    AgentSpec,
    PlanRejected,
    Registry,
    RunOptions,
    TaskContract,
    Transient,
    choose_path,
    run,
)

pytestmark = pytest.mark.criterion(8)


def registry() -> Registry:
    r = Registry()
    r.register(AgentSpec("research", "1", frozenset({"search", "verify"}), frozenset({"documents", "notes"}), frozenset({"retrieve"}), "medium"))
    r.register(AgentSpec("finance", "1", frozenset({"summarise"}), frozenset({"finance"}), frozenset({"retrieve", "calculate"}), "restricted"))
    r.register(AgentSpec("sick", "1", frozenset({"search"}), frozenset(), frozenset(), "low", healthy=False))
    r.seal()
    return r


def task(task_id, role="research", task_type="search", **kw):
    return TaskContract(task_id, task_type, role, f"objective {task_id}", **kw)


def test_the_registry_is_sealed_and_an_agent_cannot_change_its_own_authority():
    r = registry()
    with pytest.raises(PlanRejected) as e:
        r.register(AgentSpec("late", "1", frozenset({"x"}), frozenset(), frozenset()))
    assert e.value.code == "registry_sealed"
    agent = r.get("research")
    with pytest.raises(AttributeError):
        agent.sources = frozenset({"finance"})  # type: ignore[misc]  (a frozen record: nothing can widen it)
    assert agent.sources == frozenset({"documents", "notes"})


@pytest.mark.parametrize(
    ("plan", "code"),
    [
        ([task("a", task_type="delete_everything")], "task_type_not_supported"),  # a model can select only registered task types
        ([task("a", role="nobody")], "unknown_or_unhealthy_agent"),
        ([task("a", role="sick")], "unknown_or_unhealthy_agent"),
        ([task("a", sources=frozenset({"finance"}))], "authority_above_agent_registration"),
        ([task("a", tools=frozenset({"calculate"}))], "authority_above_agent_registration"),
        ([task("a", sensitivity="restricted")], "sensitivity_above_agent_ceiling"),
        ([task("a", sources=frozenset({"documents"})), task("b", parent="a", sources=frozenset({"notes"}))], "child_exceeds_parent"),
        ([task("a", sensitivity="low"), task("b", parent="a", sensitivity="medium")], "child_exceeds_parent"),
        ([task("a", depends_on=("zzz",))], "bad_dependency"),
        ([task("a", depends_on=("b",)), task("b", depends_on=("a",))], "dependency_cycle"),
        ([task("a"), task("a")], "duplicate_task"),
        ([], "plan_size"),
    ],
)
def test_a_plan_that_does_not_fit_the_registry_is_refused_before_anything_runs(plan, code):
    ran = []
    with pytest.raises(PlanRejected) as e:
        run(plan, registry(), {"research": ran.append, "finance": ran.append})
    assert e.value.code == code and ran == []


def test_dependent_tasks_wait_and_receive_only_their_declared_inputs_while_independent_ones_run_together():
    gate, started = threading.Barrier(2, timeout=5), []

    def research(ctx):
        started.append(ctx.contract.task_id)
        if ctx.contract.task_id in ("a", "b"):
            gate.wait()  # both independent tasks must be running at the same moment for this to pass
        return f"result-{ctx.contract.task_id}"

    plan = [task("a"), task("b"), task("c", depends_on=("a",))]
    report = run(plan, registry(), {"research": research})
    assert report.status == "completed" and report.tasks["c"].output == "result-c"
    seen = {}
    plan2 = [task("a"), task("c", depends_on=("a",))]
    run(plan2, registry(), {"research": lambda ctx: (seen.setdefault(ctx.contract.task_id, dict(ctx.inputs)) and None) or "out-" + ctx.contract.task_id})
    assert seen["a"] == {} and seen["c"] == {"a": "out-a"}  # only the declared dependency's output, nothing else


def test_a_transient_failure_is_retried_a_bounded_number_of_times_and_a_final_failure_is_not():
    calls = {"n": 0}

    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Transient("worker crashed")
        return "ok"

    assert run([task("a")], registry(), {"research": flaky}).tasks["a"].attempts == 3
    always = run([task("a")], registry(), {"research": lambda ctx: (_ for _ in ()).throw(Transient("busy"))})
    assert (
        always.status == "failed" and always.tasks["a"].code == "retries_exhausted" and always.tasks["a"].attempts == 3
    )  # one try plus two retries, never more
    final = run([task("a")], registry(), {"research": lambda ctx: (_ for _ in ()).throw(ValueError("SECRET-DETAIL"))})
    assert final.tasks["a"].code == "executor_failed" and final.tasks["a"].attempts == 1 and "SECRET-DETAIL" not in repr(final)


def test_an_incomplete_workflow_is_never_reported_as_complete():
    def research(ctx):
        if ctx.contract.task_id == "b":
            raise ValueError("no")
        return "ok"

    report = run([task("a"), task("b"), task("c", depends_on=("b",)), task("d", depends_on=("a",))], registry(), {"research": research})
    states = {i: r.state for i, r in report.tasks.items()}
    assert report.status == "partially_completed" and states == {"a": "completed", "b": "failed", "c": "skipped", "d": "completed"}
    assert report.tasks["c"].code == "dependency_not_completed"
    assert run([task("a")], registry(), {"research": lambda ctx: (_ for _ in ()).throw(ValueError("x"))}).status == "failed"


def test_a_high_impact_task_is_complete_only_when_independently_verified():
    plan = [task("a", high_impact=True)]
    unverified = run(plan, registry(), {"research": lambda ctx: "42"})
    assert unverified.status == "partially_completed" and unverified.reasons == ["high_impact_not_verified"] and unverified.tasks["a"].verified is False
    wrong = run(plan, registry(), {"research": lambda ctx: "42"}, RunOptions(verifier=lambda contract, output: output == "43"))
    assert wrong.status == "partially_completed"
    right = run(plan, registry(), {"research": lambda ctx: "42"}, RunOptions(verifier=lambda contract, output: output == "42"))
    assert right.status == "completed" and right.tasks["a"].verified is True


def test_cancellation_and_the_deadline_stop_the_work_and_say_so():
    stop = threading.Event()

    def research(ctx):
        if ctx.contract.task_id == "a":
            stop.set()  # the owner cancels while the first task runs
        return "ok"

    cancelled = run([task("a"), task("b", depends_on=("a",))], registry(), {"research": research}, RunOptions(cancelled=stop.is_set))
    assert cancelled.status == "cancelled" and cancelled.tasks["b"].state in ("cancelled", "skipped")
    now = [datetime(2026, 11, 23, 3, 0, tzinfo=UTC)]

    def slow(ctx):
        now[0] += timedelta(seconds=200)  # the clock jumps past the budget
        return "late"

    expired = run([task("a"), task("b", depends_on=("a",))], registry(), {"research": slow}, RunOptions(clock=lambda: now[0], total_seconds=100))
    assert expired.status == "expired" and expired.tasks["b"].state in ("expired", "skipped")


def test_restricted_domain_work_stays_inside_the_agent_registered_for_it():
    ran = []
    plan = [task("f", role="finance", task_type="summarise", sources=frozenset({"finance"}), tools=frozenset({"calculate"}), sensitivity="restricted")]
    assert run(plan, registry(), {"finance": lambda ctx: ran.append(ctx.contract.sources) or "sum"}).status == "completed" and ran == [frozenset({"finance"})]
    with pytest.raises(PlanRejected):  # the research agent can never be given finance, whatever the plan says
        run([task("x", sources=frozenset({"finance"}), sensitivity="restricted")], registry(), {"research": lambda ctx: None})


def test_the_direct_path_comes_first_when_the_plan_is_not_trusted():
    assert choose_path(0.9) == "plan" and choose_path(0.59) == "direct" and choose_path(0.1, direct_ok=False) == "ask_owner"


def test_many_tasks_run_in_bounded_time_with_bounded_workers():
    plan = [task(f"t{i}") for i in range(32)]
    started = time.monotonic()
    report = run(plan, registry(), {"research": lambda ctx: ctx.contract.task_id}, RunOptions(workers=4))
    assert report.status == "completed" and time.monotonic() - started < 5
    with pytest.raises(PlanRejected):
        run([task(f"t{i}") for i in range(33)], registry(), {"research": lambda ctx: None})


def test_a_blocked_executor_cannot_hold_the_run_past_its_deadline_or_the_owners_cancel():
    """ATLAS-ORCH-021: per-task and total budgets and cancellation are enforced while an executor is running, not only before it starts; a dependent never starts after expiry or cancel."""
    import time

    release, started = threading.Event(), []

    def blocked(ctx):
        started.append(ctx.contract.task_id)
        release.wait(10)
        return "late"

    try:
        begun = time.monotonic()
        expired = run(
            [task("a", seconds=0.1), task("b", depends_on=("a",))], registry(), {"research": blocked}
        )  # the task's own budget is shorter than the run's
        assert time.monotonic() - begun < 2 and expired.status == "expired" and expired.tasks["a"].state == "expired" and expired.tasks["b"].state == "skipped"
        assert started == ["a"]  # the dependent never started

        begun = time.monotonic()
        total = run([task("a", seconds=60)], registry(), {"research": blocked}, RunOptions(total_seconds=0.1))
        assert time.monotonic() - begun < 2 and total.status == "expired" and total.tasks["a"].code == "deadline"

        stop = threading.Timer(0.05, lambda: None)
        flag = threading.Event()
        stop = threading.Timer(0.05, flag.set)
        stop.start()
        begun = time.monotonic()
        cancelled = run([task("a", seconds=60), task("b", depends_on=("a",))], registry(), {"research": blocked}, RunOptions(cancelled=flag.is_set))
        assert (
            time.monotonic() - begun < 2
            and cancelled.status == "cancelled"
            and cancelled.tasks["a"].state == "cancelled"
            and cancelled.tasks["b"].state == "skipped"
        )
    finally:
        release.set()


def test_an_executor_that_returns_after_its_deadline_is_expired_and_its_result_is_not_used():
    now = [datetime(2026, 11, 23, 3, 0, tzinfo=UTC)]

    def late(ctx):
        now[0] += timedelta(seconds=45)  # returns, but past its own 30 second budget
        return "too late"

    report = run([task("a")], registry(), {"research": late}, RunOptions(clock=lambda: now[0], total_seconds=3600))
    assert report.status == "expired" and report.tasks["a"].state == "expired" and report.tasks["a"].output is None
