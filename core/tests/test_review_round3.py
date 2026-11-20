"""Third independent review: (1) a sensitivity label is trusted only if it comes from the source store, never from the retriever; (2) a token is bound to the grant it was minted under
(identity and ceiling), so a revoke and a new grant, or a changed ceiling, ends its authority before the next read and before the model; (3) a terminal state and its one closing event
are committed together on EVERY terminal path, and the store refuses a terminal transition that does not carry exactly one."""

from __future__ import annotations

import dataclasses

import pytest
from conftest import CORPUS, T0, FixtureStore, StubModel, World, grant, labels, passage, request

from atlas_core.errors import CoreError
from atlas_core.gate import GatedModel, GatedRetrieval
from atlas_core.policy import InMemoryGrants, PermissionRevoked, PolicyEngine
from atlas_core.service import SimulatedCrash
from atlas_core.tasks import TERMINAL

DOC, MAIL = CORPUS[0], CORPUS[2]


def regrant(w: World, source_type: str, new_id: str, sensitivity: str = "high") -> None:
    """The owner revokes the grant a task started under and makes a new one (another identity, possibly another ceiling)."""
    for g in w.grants._grants:
        if g["source_type"] == source_type:
            g["revoked"] = True
    w.grants.add({**grant(source_type, sensitivity=sensitivity), "grant_id": new_id})


class Crafted:
    """A retriever that returns exactly what it is given (a hostile or buggy one)."""

    def __init__(self, items: list[dict]) -> None:
        self.items, self.calls = items, []

    def search(self, source_type: str, query: str) -> list[dict]:
        self.calls.append(source_type)
        return self.items


# ---- 1. trusted per-item sensitivity ---------------------------------------------------------------------------------------------------------------
@pytest.mark.criterion(1)
@pytest.mark.parametrize("claimed", ["low", "medium", None])
def test_a_retriever_that_understates_an_items_sensitivity_is_not_believed(tmp_path, claimed):
    w = World(tmp_path, [grant("documents", sensitivity="medium")])
    w.sources.sources["doc00001"] = dataclasses.replace(DOC, sensitivity="high")  # the store knows the item is highly sensitive
    if claimed:
        w.retriever.sens = {"doc00001": claimed}  # the retriever mislabels it
    w.model.answer_text, w.model.quote = "Het totaal staat in het document.", "Totaal bedrag"
    record = w.run_new(request(["documents"]))
    assert "doc00001" not in {p["evidence"]["source_id"] for ctx in w.model.calls for p in ctx.passages}
    assert "sensitive_items_excluded" in w.service.answer(record["task_id"])["limitations"]


@pytest.mark.criterion(1)
def test_a_retriever_cannot_raise_an_items_label_either_the_store_decides_both_ways(tmp_path):
    w = World(tmp_path, [grant("documents", sensitivity="medium")])
    w.retriever.sens = {"doc00001": "restricted"}  # a retriever that over-states: ignored, the store's label (the type default, medium) applies
    record = w.run_new(request(["documents"]))
    assert "doc00001" in {p["evidence"]["source_id"] for ctx in w.model.calls for p in ctx.passages}
    assert "sensitive_items_excluded" not in w.service.answer(record["task_id"])["limitations"]


@pytest.mark.criterion(1)
def test_an_item_whose_source_is_unknown_or_whose_type_disagrees_with_the_store_fails_closed():
    token = PolicyEngine(InMemoryGrants([grant("documents"), grant("mail")])).decide(["documents", "mail"], T0)[1]
    assert token is not None
    good = passage(DOC, 0, 10)
    unknown = {**good, "evidence": {**good["evidence"], "source_id": "nosuchsrc1"}}  # the store has no such source
    confused = {**good, "evidence": {**good["evidence"], "source_type": "mail"}}  # claims to be mail, the store says documents
    result = GatedRetrieval(labels()).fetch(token, Crafted([good, unknown, confused]), "q", T0)
    assert [p["evidence"]["source_id"] for p in result.passages] == [
        "doc00001",
        "doc00001",
    ] and result.excluded_sensitive >= 2  # one real passage per searched type; both forgeries refused


@pytest.mark.criterion(1)
def test_an_unknown_label_in_the_store_and_a_missing_label_are_never_covered_by_any_grant():
    store = FixtureStore()
    store.sources[DOC.source_id] = dataclasses.replace(DOC, sensitivity="ultra")
    assert labels(store).of(passage(DOC, 0, 10)) is None
    token = PolicyEngine(InMemoryGrants([grant("documents", sensitivity="restricted")])).decide(["documents"], T0)[1]
    assert token is not None
    assert token.allows_item("documents", "low", T0) and token.allows_item("documents", "restricted", T0)
    for bad_label in (None, "", "ultra", "HIGH", "unlabelled"):
        assert not token.allows_item("documents", bad_label, T0)


@pytest.mark.criterion(1)
def test_the_gate_never_reads_a_sensitivity_from_the_passage_itself(tmp_path):
    w = World(tmp_path, [grant("documents", sensitivity="medium")])
    w.sources.sources["doc00001"] = dataclasses.replace(DOC, sensitivity="high")
    token = PolicyEngine(w.grants).decide(["documents"], T0)[1]
    assert token is not None
    forged = {**passage(DOC, 0, 10), "sensitivity": "low"}  # a passage carrying its own low label
    from atlas_core.gate import ContextBuilder

    with pytest.raises(Exception, match="passage_not_permitted"):
        ContextBuilder(labels(w.sources)).build(token, "q", [forged], T0)
    model = StubModel()
    context_ok = ContextBuilder(labels(w.sources)).build(
        token, "q", [passage(CORPUS[1], 0, 10)], T0
    )  # an allowed item, then the door re-checks with the store too
    GatedModel(model, labels(w.sources)).generate(token, context_ok, T0)
    assert len(model.calls) == 1


# ---- 2. the token is bound to the grant it was minted under -----------------------------------------------------------------------------------------
@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_a_revoke_and_a_new_grant_ends_the_old_authority_even_though_the_type_is_still_allowed(tmp_path):
    w = World(tmp_path, [grant("documents")])
    engine = PolicyEngine(w.grants)
    token = engine.decide(["documents"], T0)[1]
    assert token is not None and engine.revalidate(token, T0)[0] == frozenset({"documents"})
    regrant(w, "documents", "grant-documents-02")  # the type is allowed again under a different grant
    assert engine.decide(["documents"], T0)[1] is not None  # a NEW decision would be allowed...
    current, denied = engine.revalidate(token, T0)
    assert current == frozenset() and denied == [{"source_type": "documents", "reason_code": "grant_revoked"}]  # ...but the old token is not
    spy = Crafted([passage(DOC, 0, 10)])
    with pytest.raises(PermissionRevoked):
        GatedRetrieval(labels()).fetch(token, spy, "q", T0, engine)
    assert spy.calls == []  # nothing was read under the stale authority
    model = StubModel()
    from atlas_core.gate import ContextBuilder

    context = ContextBuilder(labels()).build(token, "q", [passage(DOC, 0, 10)], T0)
    with pytest.raises(PermissionRevoked):
        GatedModel(model, labels(), engine).generate(token, context, T0)
    assert model.calls == []


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_a_ceiling_changed_in_place_ends_the_authority_the_model_gets_nothing(tmp_path):
    w = World(tmp_path, [grant("documents", sensitivity="high")])
    engine = PolicyEngine(w.grants)
    token = engine.decide(["documents"], T0)[1]
    assert token is not None
    w.grants._grants[0]["max_sensitivity"] = "medium"  # the same grant, scope lowered (replaced) between mint and use
    assert engine.revalidate(token, T0) == (frozenset(), [{"source_type": "documents", "reason_code": "grant_revoked"}])
    model = StubModel()
    from atlas_core.gate import ContextBuilder

    context = ContextBuilder(labels()).build(token, "q", [passage(DOC, 0, 10)], T0)  # built from the minted authority
    with pytest.raises(PermissionRevoked):
        GatedModel(model, labels(), engine).generate(token, context, T0)
    assert model.calls == []


@pytest.mark.criterion(1)
def test_a_broader_newer_grant_does_not_extend_an_old_token_and_an_unchanged_grant_keeps_it_valid():
    grants = InMemoryGrants([grant("documents", sensitivity="medium")])
    engine = PolicyEngine(grants)
    token = engine.decide(["documents"], T0)[1]
    assert token is not None
    grants.add({**grant("documents", sensitivity="restricted"), "grant_id": "grant-documents-99"})  # a second, broader grant appears; the first is untouched
    assert engine.revalidate(token, T0) == (frozenset({"documents"}), [])  # still valid: the SAME grant with the SAME ceiling
    assert not token.allows_item("documents", "high", T0)  # and it gained nothing from the broader grant
    grants._grants[0]["revoked"] = True  # now the first is revoked while the broader one remains
    assert engine.revalidate(token, T0)[0] == frozenset()


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_a_new_grant_between_two_source_reads_stops_the_next_read(tmp_path):
    w = World(tmp_path, [grant("documents"), grant("mail")])
    w.retriever.on_search = lambda st: regrant(w, "mail", "grant-mail-02") if st == "documents" else None  # revoke and regrant mail after documents was read
    record = w.run_new(request(["documents", "mail"]))
    assert w.retriever.calls == ["documents"] and w.model.calls == []
    assert (record["state"], record["terminal_reason"]) == ("failed", "denied")


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_a_new_grant_after_retrieval_and_before_the_model_gives_the_model_zero_passages(tmp_path):
    w = World(tmp_path, [grant("documents"), grant("mail")])
    w.retriever.on_search = lambda st: (
        regrant(w, "documents", "grant-documents-02") if st == "mail" else None
    )  # documents already read, then revoked and regranted
    record = w.run_new(request(["documents", "mail"]))
    assert w.retriever.calls == ["documents", "mail"] and w.model.calls == []
    answer = w.service.answer(record["task_id"])
    assert (record["state"], record["terminal_reason"]) == ("failed", "denied") and answer["answer"].startswith("The task was stopped")
    assert {n["source_type"] for n in answer["withheld_sources"]} == {"documents"}


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_a_ceiling_lowered_during_retrieval_stops_the_run_and_the_model_gets_nothing(tmp_path):
    w = World(tmp_path, [grant("documents", sensitivity="high"), grant("mail", sensitivity="high")])

    def lower(source_type: str) -> None:
        if source_type == "documents":
            for g in w.grants._grants:
                g["max_sensitivity"] = "medium"

    w.retriever.on_search = lower
    record = w.run_new(request(["documents", "mail"]))
    assert w.model.calls == [] and (record["state"], record["terminal_reason"]) == ("failed", "denied")


# ---- 3. a terminal state and its one closing event are atomic on every terminal path ---------------------------------------------------------------
def _submit(w: World, **kw) -> str:
    return str(w.service.submit(request(**kw))[0]["task_id"])


def path_completed(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = _submit(w)
    return w, tid, lambda: w.service.run(tid)


def path_partial(tmp_path):
    w = World(tmp_path, [grant("documents")])
    w.model.mode = "extra_figure"
    tid = _submit(w)
    return w, tid, lambda: w.service.run(tid)


def path_citation_failed(tmp_path):
    w = World(tmp_path, [grant("documents")])
    w.model.mode = "bad_quote"
    tid = _submit(w)
    return w, tid, lambda: w.service.run(tid)


def path_model_unavailable(tmp_path):
    w = World(tmp_path, [grant("documents")])
    w.model.mode = "unavailable"
    tid = _submit(w)
    return w, tid, lambda: w.service.run(tid)


def path_denied(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = _submit(w)
    w.grants._grants[:] = []  # the permission is gone before the task runs
    return w, tid, lambda: w.service.run(tid)


def path_cancelled_immediately(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = _submit(w)
    return w, tid, lambda: w.service.cancel(tid)


def path_cancelled_at_a_boundary(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = _submit(w)
    w.retriever.on_search = lambda st: w.service.cancel(tid)  # cancellation requested while the task runs
    return w, tid, lambda: w.service.run(tid)


def path_expired(tmp_path):
    w = World(tmp_path, [grant("documents")])
    tid = _submit(w, seconds=5)
    w.clock.advance(100)
    return w, tid, lambda: w.service.expire_due()  # noqa: PLW0108  (w.service is replaced on restart, so it is looked up each time)


def path_recovered_into_needs_attention(tmp_path):
    from atlas_core.service import SimulatedCrash as Crash

    w = World(tmp_path, [grant("documents")])
    tid = _submit(w, max_retries=0)
    w.faults.armed.add("before:final")
    with pytest.raises(Crash):
        w.service.run(tid)  # the process dies after verification; with no retries left, recovery ends the task
    return w, tid, lambda: w.service.recover()  # noqa: PLW0108  (w.service is replaced on restart, so it is looked up each time)


PATHS = {
    "completed": path_completed, "partially_completed": path_partial, "failed_citation": path_citation_failed, "failed_model": path_model_unavailable, "failed_denied": path_denied,
    "cancelled_immediately": path_cancelled_immediately, "cancelled_at_a_boundary": path_cancelled_at_a_boundary, "expired": path_expired, "needs_attention_on_recovery": path_recovered_into_needs_attention,
}  # fmt: skip


@pytest.mark.criterion(3)
@pytest.mark.parametrize("point", ["after_state", "after_events"])
@pytest.mark.parametrize("path", sorted(PATHS))
def test_a_crash_inside_any_terminal_transition_leaves_neither_a_terminal_state_nor_a_half_written_event(tmp_path, path, point):
    w, task_id, trigger = PATHS[path](tmp_path)
    before = (w.store.record(task_id)["state"], w.store.events_after(task_id, 0))

    def die(name: str) -> None:
        if name == point and w.store.record(task_id)["state"] in TERMINAL:
            raise SimulatedCrash(name)  # the process dies inside the transaction that would commit the terminal state

    w.store.hook = die
    with pytest.raises(SimulatedCrash):
        trigger()
    assert w.store.record(task_id)["state"] not in TERMINAL  # rolled back: no terminal state without its event...
    with pytest.raises(CoreError):
        w.service.answer(task_id)  # ...and no answer is served for a task that has not finished (a saved checkpoint envelope is never a result)
    closing = [e for e in w.store.events_after(task_id, 0) if e["type"] in ("final", "error")]
    assert closing == [e for e in before[1] if e["type"] in ("final", "error")]  # ...and no closing event without its state
    w.store.hook = None
    w.restart()
    trigger()
    record = w.store.record(task_id)
    events = w.store.events_after(task_id, 0)
    assert record["state"] in TERMINAL
    assert [e["type"] for e in events].count("final") + [e["type"] for e in events].count("error") == 1  # exactly one closing event
    assert events[-1]["type"] in ("final", "error") and [e["seq"] for e in events] == list(range(1, len(events) + 1))
    if path not in ("cancelled_immediately", "cancelled_at_a_boundary", "expired", "needs_attention_on_recovery", "failed_model"):
        assert w.service.answer(task_id)["task_id"] == task_id  # a finished task with an answer serves it


@pytest.mark.criterion(3)
def test_the_store_refuses_a_terminal_transition_that_does_not_carry_exactly_one_closing_event(tmp_path):
    w = World(tmp_path, [grant("documents")])
    error = {"type": "error", "error": {"code": "task_failed", "message": "x", "retryable": False, "correlation_id": "corr00001"}}
    for events in ([], [{"type": "state", "state": "failed"}], [error, error], [{"type": "final"}, error]):
        task_id = _submit(w, key=f"idem-key-{abs(hash(str(events))) % 10**6:06d}")
        with pytest.raises(CoreError):
            w.store.transition(task_id, "failed", w.clock(), reason="needs_attention", events=events)
        assert w.store.record(task_id)["state"] not in TERMINAL  # nothing committed
    assert not hasattr(w.store, "append_event")  # the one writer of an event outside a state change is gone


def test_every_terminal_path_of_the_service_goes_through_the_atomic_transition():
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "src" / "atlas_core" / "service.py").read_text()
    assert not re.search(r"store\.(append_event|_append_in_txn|_apply)\b", source)  # the service never writes an event or a state on its own
    assert len(re.findall(r"store\.transition\(", source)) == 1  # and has exactly one way to change state: _to


@pytest.mark.criterion(3)
def test_a_denied_tasks_safe_answer_commits_with_its_state_and_an_unfinished_task_serves_no_answer(tmp_path):
    w = World(tmp_path, [grant("documents")])
    task_id = _submit(w)
    w.grants._grants[:] = []

    def die(name: str) -> None:
        if name == "after_events" and w.store.record(task_id)["state"] in TERMINAL:
            raise SimulatedCrash(name)

    w.store.hook = die
    with pytest.raises(SimulatedCrash):
        w.service.run(task_id)
    with pytest.raises(CoreError):
        w.store.answer(task_id)  # the safe answer was not saved on its own: it commits with the state or not at all
    w.store.hook = None
    w.restart()
    w.service.run(task_id)
    assert w.service.answer(task_id)["answer"].startswith("Nothing was searched")


@pytest.mark.criterion(3)
def test_a_saved_checkpoint_answer_of_an_unfinished_task_is_never_served_through_the_api(tmp_path):
    w = World(tmp_path, [grant("documents")])
    task_id = _submit(w, max_retries=5)
    w.faults.armed.add("before:final")
    with pytest.raises(SimulatedCrash):
        w.service.run(task_id)  # verified and saved, not yet finished
    assert w.store.record(task_id)["state"] == "verified" and w.store.answer(task_id)["task_id"] == task_id
    with pytest.raises(CoreError):
        w.service.answer(task_id)
