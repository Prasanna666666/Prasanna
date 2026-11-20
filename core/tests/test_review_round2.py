"""Second independent review: per-item sensitivity at the gate, revocation re-checked at the active retrieval/model boundary, and state changes committed atomically with their events."""

from __future__ import annotations

import dataclasses

import pytest
from conftest import CORPUS, T0, StubModel, World, grant, passage, request

from atlas_core.gate import ContextBuilder, GatedModel
from atlas_core.policy import InMemoryGrants, PermissionRevoked, PolicyEngine, PolicyViolation
from atlas_core.service import SimulatedCrash
from atlas_core.tasks import TERMINAL

DOC, MAIL = CORPUS[0], CORPUS[2]


def _drop(w: World, source_type: str) -> None:
    w.grants._grants[:] = [g for g in w.grants._grants if g["source_type"] != source_type]


def _dutch_answer(w: World) -> None:
    w.model.answer_text, w.model.quote = "Het totaal staat in het document.", "Totaal bedrag"


# ---- 1. per-item sensitivity ----------------------------------------------------------------------------------------------------------------
@pytest.mark.criterion(1)
def test_an_item_more_sensitive_than_the_grant_is_excluded_at_the_gate_and_disclosed(tmp_path):
    w = World(tmp_path, [grant("documents", sensitivity="medium")])
    w.retriever.sens = {"doc00001": "high"}  # a highly sensitive document that arrives as source type 'documents'
    _dutch_answer(w)
    record = w.run_new(request(["documents"]))
    sent = {p["evidence"]["source_id"] for ctx in w.model.calls for p in ctx.passages}
    assert sent == {"docnl001"}  # the high-sensitivity document never reached the model
    answer = w.service.answer(record["task_id"])
    assert "sensitive_items_excluded" in answer["limitations"] and all(c["evidence"]["source_id"] != "doc00001" for c in answer["citations"])


@pytest.mark.criterion(1)
def test_the_same_item_is_used_when_the_grant_covers_its_sensitivity(tmp_path):
    w = World(tmp_path, [grant("documents", sensitivity="high")])
    w.retriever.sens = {"doc00001": "high"}
    record = w.run_new(request(["documents"]))
    assert "doc00001" in {p["evidence"]["source_id"] for ctx in w.model.calls for p in ctx.passages}
    assert "sensitive_items_excluded" not in w.service.answer(record["task_id"])["limitations"]


@pytest.mark.criterion(1)
def test_the_builder_and_the_model_door_each_refuse_an_item_above_the_grant():
    engine = PolicyEngine(InMemoryGrants([grant("documents", sensitivity="medium")]))
    _, medium = engine.decide(["documents"], T0)
    _, high = PolicyEngine(InMemoryGrants([grant("documents", sensitivity="high")])).decide(["documents"], T0)
    assert medium is not None and high is not None
    item = {**passage(DOC, 0, 10), "sensitivity": "high"}
    with pytest.raises(PolicyViolation):
        ContextBuilder().build(medium, "q", [item], T0)
    context = ContextBuilder().build(high, "q", [item], T0)  # legitimately built under the broad grant
    forged = dataclasses.replace(context, permit_id=medium.permit_id)  # then presented with the narrow token and its id
    model = StubModel()
    with pytest.raises(PolicyViolation):
        GatedModel(model).generate(medium, forged, T0)
    assert model.calls == []


# ---- 2. revocation at the active boundary ---------------------------------------------------------------------------------------------------
@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_a_grant_revoked_during_retrieval_stops_the_next_source_read(tmp_path):
    w = World(tmp_path, [grant("documents"), grant("mail")])
    w.retriever.on_search = lambda source_type: (
        _drop(w, "mail") if source_type == "documents" else None
    )  # revoked after the token was minted, before mail is read
    record = w.run_new(request(["documents", "mail"]))
    assert w.retriever.calls == ["documents"]  # mail was never read
    assert w.model.calls == []  # and nothing reached the model
    answer = w.service.answer(record["task_id"])
    assert (record["state"], record["terminal_reason"]) == ("failed", "denied") and answer["answer"].startswith("The task was stopped")
    assert answer["withheld_sources"] == [] and answer["not_searched"] == []  # nothing was durably recorded: both were only attempted


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_a_grant_revoked_after_retrieval_and_before_the_model_never_reaches_the_model(tmp_path):
    w = World(tmp_path, [grant("documents"), grant("mail")])
    w.retriever.on_search = lambda source_type: _drop(w, "documents") if source_type == "mail" else None  # documents already read, then revoked
    record = w.run_new(request(["documents", "mail"]))
    assert w.retriever.calls == ["documents", "mail"] and w.model.calls == []  # the revoked passages were fetched but never sent
    answer = w.service.answer(record["task_id"])
    assert (record["state"], record["terminal_reason"]) == ("failed", "denied") and answer["answer"].startswith("The task was stopped")
    assert {n["source_type"] for n in answer["withheld_sources"]} == {"documents"}  # confirmed retrieved, now withheld


@pytest.mark.criterion(1)
def test_the_model_door_with_a_policy_refuses_a_token_whose_grant_was_revoked_after_it_was_minted():
    grants = InMemoryGrants([grant("documents")])
    engine = PolicyEngine(grants)
    _, token = engine.decide(["documents"], T0)
    assert token is not None
    context = ContextBuilder().build(token, "q", [passage(DOC, 0, 10)], T0)
    grants._grants.clear()  # revoked while the token (valid for minutes) is still in hand
    model = StubModel()
    with pytest.raises(PermissionRevoked):
        GatedModel(model, engine).generate(token, context, T0)
    assert model.calls == []
    GatedModel(model).generate(token, context, T0)  # without a policy only the token's own snapshot is checked: why the service always passes one
    assert len(model.calls) == 1


# ---- 3. state changes and their events are atomic -------------------------------------------------------------------------------------------
def _terminal_hook(w: World, task_id: str):
    def hook(name: str) -> None:
        if name == "after_state" and w.store.record(task_id)["state"] in TERMINAL:
            raise SimulatedCrash(name)  # the process dies after the state UPDATE, before the transaction commits

    return hook


@pytest.mark.criterion(3)
def test_a_crash_inside_the_terminal_transition_leaves_neither_the_state_nor_the_final_event(tmp_path):
    w = World(tmp_path, [grant("documents")])
    record, _ = w.service.submit(request(max_retries=5))
    task_id = record["task_id"]
    w.faults.armed.add("before:final")
    with pytest.raises(SimulatedCrash):
        w.service.run(task_id)
    w.restart()
    w.store.hook = _terminal_hook(w, task_id)
    with pytest.raises(SimulatedCrash):
        w.service.run(task_id)  # dies inside the transaction that would commit 'completed' and its final event
    assert w.store.record(task_id)["state"] == "verified"  # rolled back: still the last committed state
    assert not any(e["type"] == "final" for e in w.store.events_after(task_id, 0))  # and no half-written event
    w.store.hook = None
    w.restart()
    assert w.service.run(task_id)["state"] == "completed"
    events = w.store.events_after(task_id, 0)
    assert [e["type"] for e in events].count("final") == 1 and events[-1]["type"] == "final"  # exactly one, and last
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


@pytest.mark.criterion(3)
def test_a_crash_inside_the_denial_transition_is_repaired_with_its_error_event(tmp_path):
    w = World(tmp_path, [])
    w.store.hook = lambda name: (_ for _ in ()).throw(SimulatedCrash(name)) if name == "after_state" and w.store.ids_in(("failed",)) else None
    with pytest.raises(SimulatedCrash):
        w.service.submit(request(["documents"]))
    w.store.hook = None
    (task_id,) = w.store.ids_in(("requested", "policy_checked"))  # the denial's terminal transition rolled back
    w.restart()
    record = w.store.record(task_id)
    assert (record["state"], record["terminal_reason"]) == ("failed", "needs_attention")
    assert [e["error"]["code"] for e in w.store.events_after(task_id, 0) if e["type"] == "error"] == ["needs_attention"]


@pytest.mark.criterion(3)
def test_every_terminal_task_has_exactly_one_closing_event_whichever_way_it_ends(tmp_path):
    w = World(tmp_path, [grant("documents")])
    done = w.run_new(request(key="idem-key-0001"))
    cancelled, _ = w.service.submit(request(key="idem-key-0002"))
    w.service.cancel(cancelled["task_id"])
    w.model.mode = "unavailable"
    failed = w.run_new(request(key="idem-key-0003"))
    late, _ = w.service.submit(request(key="idem-key-0004", seconds=5))
    w.clock.advance(100)
    w.service.expire_due()
    for record in (done, cancelled, failed, late):
        events = w.store.events_after(record["task_id"], 0)
        closing = [e for e in events if e["type"] in ("final", "error")]
        assert w.store.record(record["task_id"])["state"] in TERMINAL and len(closing) == 1 and events[-1] is not None, record["task_id"]
