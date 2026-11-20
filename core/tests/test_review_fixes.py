"""Regression tests for the independent Stage 2 review: revocation on resume, token/context binding at the model door, and the Keychain-backed task key."""

from __future__ import annotations

import dataclasses
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from conftest import CORPUS, KEY, SENTINEL_DOC, T0, StubModel, World, grant, passage, request

from atlas_core.gate import ContextBuilder, GatedModel
from atlas_core.policy import InMemoryGrants, PolicyEngine, PolicyViolation
from atlas_core.service import SimulatedCrash
from atlas_core.tasks import (
    KEYCHAIN_ITEM,
    EnvKeyProvider,
    KeychainKeyProvider,
    StoreKeyError,
    default_provider,
    open_task_store,
    task_store_key,
)

DOC, MAIL = CORPUS[0], CORPUS[2]
BOTH = [grant("documents"), grant("mail")]


def _world(tmp_path) -> World:
    return World(tmp_path, [dict(g) for g in BOTH])


def _revoke(w: World, source_type: str) -> None:
    w.grants._grants[:] = [g for g in w.grants._grants if g["source_type"] != source_type]


@pytest.mark.criterion(1)
@pytest.mark.criterion(3)
@pytest.mark.parametrize("boundary", ["after:retrieved", "after:drafted", "before:verified", "after:verified", "before:final"])
@pytest.mark.parametrize("revoked", ["documents", "mail"])
def test_a_grant_revoked_while_another_stays_fails_closed_on_resume(tmp_path, boundary, revoked):
    w = _world(tmp_path)
    record, _ = w.service.submit(request(["documents", "mail"]))
    w.faults.armed.add(boundary)
    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    w.restart()
    _revoke(w, revoked)  # one source is revoked, the other is still allowed: the new token is not null
    final = w.service.run(record["task_id"])
    assert (final["state"], final["terminal_reason"]) == ("failed", "denied"), boundary
    answer = w.service.answer(record["task_id"])
    events = w.service.events_after(record["task_id"], 0)
    stopped = boundary == "after:retrieved"  # retrieval happened but no draft existed yet: the task stopped, there is no answer to withhold
    assert answer["answer"].startswith("The task was stopped" if stopped else "This answer is no longer available")
    assert ("task_stopped_no_answer" if stopped else "answer_withheld") in answer["limitations"] and answer["citations"] == []
    assert "Nothing was searched" not in answer["answer"]  # retrieval did happen
    assert any(n["source_type"] == revoked for n in answer["withheld_sources"]) and all(n["source_type"] != revoked for n in answer["not_searched"])
    assert SENTINEL_DOC not in repr(answer) + repr(events) and not any(e["type"] == "final" for e in events)


@pytest.mark.criterion(1)
def test_a_resume_with_every_grant_intact_still_completes(tmp_path):
    w = _world(tmp_path)
    record, _ = w.service.submit(request(["documents", "mail"]))
    w.faults.armed.add("after:drafted")
    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    w.restart()
    assert w.service.run(record["task_id"])["state"] == "completed"


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_an_answer_and_its_stream_are_withheld_once_a_source_it_cites_is_revoked(tmp_path):
    w = _world(tmp_path)
    record = w.run_new(request(["documents", "mail"]))
    assert record["state"] == "completed" and {c["evidence"]["source_type"] for c in w.service.answer(record["task_id"])["citations"]} == {"documents"}
    _revoke(w, "documents")
    withheld = w.service.answer(record["task_id"])
    events = w.service.events_after(record["task_id"], 0)
    assert withheld["answer"].startswith("This answer is no longer available") and withheld["citations"] == [] and not any(e["type"] == "final" for e in events)
    assert [e["seq"] for e in events] == sorted({e["seq"] for e in events}) and events[-1]["error"]["code"] == "source_denied"
    assert w.store.answer(record["task_id"])["verification"]["status"] == "verified"  # stored as it was; only what is served is gated


def _tokens(*grants_):
    engine = PolicyEngine(InMemoryGrants([dict(g) for g in grants_]))
    return engine.decide(["documents", "mail"], T0)[1], engine.decide(["documents"], T0)[1]


@pytest.mark.criterion(1)
@pytest.mark.criterion(2)
def test_a_context_built_under_a_broad_token_cannot_be_used_with_a_narrow_one():
    broad, narrow = _tokens(grant("documents"), grant("mail"))
    assert broad is not None and narrow is not None and broad.permit_id != narrow.permit_id
    context = ContextBuilder().build(broad, "q", [passage(DOC, 0, 10), passage(MAIL, 0, 10)], T0)
    model = StubModel()
    gated = GatedModel(model)
    for attempt in (context, dataclasses.replace(context, permit_id=narrow.permit_id)):  # even a copy that claims the narrow token's id
        with pytest.raises(PolicyViolation):
            gated.generate(narrow, attempt, T0)
    assert model.calls == []
    gated.generate(broad, context, T0)  # the token it was built under works
    assert len(model.calls) == 1


@pytest.mark.criterion(1)
def test_a_token_that_expired_or_belongs_to_another_decision_never_reaches_the_model():
    broad, narrow = _tokens(grant("documents"), grant("mail"))
    context = ContextBuilder().build(narrow, "q", [passage(DOC, 0, 10)], T0)
    model = StubModel()
    with pytest.raises(PolicyViolation):
        GatedModel(model).generate(broad, context, T0)  # same scope or broader, but a different authorisation
    with pytest.raises(PolicyViolation):
        GatedModel(model).generate(narrow, context, T0 + timedelta(hours=1))
    assert model.calls == []


class FakeSecurity:
    """A stand-in for the macOS `security` tool: records every call; behaves like a Keychain with or without the item."""

    def __init__(self, stored: str | None = None) -> None:
        self.stored, self.calls = stored, []

    def __call__(self, argv, input=None, **kwargs):
        self.calls.append((list(argv), input))
        if argv[1] == "find-generic-password":
            return SimpleNamespace(returncode=0, stdout=self.stored + "\n") if self.stored else SimpleNamespace(returncode=44, stdout="")
        match = re.search(r"-w ([0-9a-f]{64})", input or "")
        assert argv == ["security", "-i"] and match
        self.stored = match.group(1)
        return SimpleNamespace(returncode=0, stdout="")


@pytest.mark.criterion(11)
def test_the_keychain_provider_reads_the_dedicated_item_and_never_a_file_or_the_environment():
    runner = FakeSecurity(stored="k" * 64)
    assert KeychainKeyProvider("owner", runner).get() == "k" * 64
    argv = runner.calls[0][0]
    assert argv[:2] == ["security", "find-generic-password"] and argv[argv.index("-s") : argv.index("-s") + 2] == ["-s", KEYCHAIN_ITEM] and argv[-1] == "-w"
    with pytest.raises(StoreKeyError, match="not been provisioned"):
        KeychainKeyProvider("owner", FakeSecurity()).get()


@pytest.mark.criterion(11)
def test_provisioning_creates_a_random_key_once_and_never_puts_it_on_a_command_line():
    runner = FakeSecurity()
    provider = KeychainKeyProvider("owner name", runner)
    assert provider.provision() is True and provider.provision() is False
    adds = [(argv, text) for argv, text in runner.calls if argv[1:] == ["-i"]]
    assert len(adds) == 1 and runner.stored is not None and len(runner.stored) == 64
    assert all(runner.stored not in " ".join(argv) for argv, _ in runner.calls)  # the key travels on standard input only
    assert KEYCHAIN_ITEM in adds[0][1] and "'owner name'" in adds[0][1]
    assert provider.get() == runner.stored


@pytest.mark.criterion(11)
def test_on_a_mac_the_environment_or_a_key_file_never_silently_replaces_the_keychain():
    env = {"ATLAS_TASK_KEY": KEY, "ATLAS_TASK_KEY_FILE": "/nonexistent"}
    assert isinstance(default_provider("darwin", env), KeychainKeyProvider)
    assert isinstance(default_provider("darwin", {**env, "ATLAS_TASK_KEY_SOURCE": "env"}), EnvKeyProvider)  # only by an explicit opt-in
    assert isinstance(default_provider("linux", env), EnvKeyProvider)
    with pytest.raises(StoreKeyError):
        task_store_key(KeychainKeyProvider("owner", FakeSecurity()))  # not provisioned: no fallback, even though an env key exists


@pytest.mark.criterion(11)
def test_the_store_opens_with_a_key_from_any_provider_and_not_without_one(tmp_path):
    store = open_task_store(tmp_path / "tasks.db", KeychainKeyProvider("owner", FakeSecurity(stored=KEY)))
    store.close()
    with pytest.raises(StoreKeyError):
        open_task_store(tmp_path / "other.db", KeychainKeyProvider("owner", FakeSecurity()))
    assert EnvKeyProvider({"ATLAS_TASK_KEY": KEY}).get() == KEY


UNCITED = f"Note {SENTINEL_DOC} was in the file."


def _uncited_world(tmp_path) -> World:
    w = _world(tmp_path)
    w.model.mode, w.model.answer_text = "no_citation", UNCITED
    return w


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
def test_an_uncited_answer_is_served_while_every_source_it_came_from_is_permitted(tmp_path):
    w = _uncited_world(tmp_path)
    record = w.run_new(request(["documents", "mail"]))
    answer = w.service.answer(record["task_id"])
    assert (record["state"], answer["verification"]["status"], answer["citations"]) == ("partially_completed", "unverified", [])
    assert answer["answer"] == UNCITED and any(e["type"] == "final" and e["answer"]["answer"] == UNCITED for e in w.service.events_after(record["task_id"], 0))


@pytest.mark.criterion(1)
@pytest.mark.criterion(16)
@pytest.mark.parametrize("revoked", ["documents", "mail"])
def test_an_uncited_answer_and_its_final_event_are_withheld_once_any_source_it_came_from_is_revoked(tmp_path, revoked):
    w = _uncited_world(tmp_path)
    record = w.run_new(request(["documents", "mail"]))
    _revoke(w, revoked)  # one source goes, the other stays allowed
    answer = w.service.answer(record["task_id"])
    events = w.service.events_after(record["task_id"], 0)
    assert answer["answer"].startswith("This answer is no longer available") and SENTINEL_DOC not in repr(answer) + repr(events)
    assert not any(e["type"] == "final" for e in events) and events[-1]["error"]["code"] == "source_denied"
    assert any(n["source_type"] == revoked for n in answer["withheld_sources"]) and all(n["source_type"] != revoked for n in answer["not_searched"])
    assert w.store.answer(record["task_id"])["answer"] == UNCITED  # stored unchanged for audit; only what is served is gated


@pytest.mark.criterion(1)
def test_a_single_source_uncited_answer_is_withheld_when_that_source_is_revoked(tmp_path):
    w = World(tmp_path, [grant("documents"), grant("mail")])
    w.model.mode, w.model.answer_text = "no_citation", UNCITED
    record = w.run_new(request(["documents"]))
    assert w.service.answer(record["task_id"])["answer"] == UNCITED
    _revoke(w, "documents")
    assert SENTINEL_DOC not in repr(w.service.answer(record["task_id"])) + repr(w.service.events_after(record["task_id"], 0))


@pytest.mark.criterion(9)
def test_the_wording_is_accurate_for_each_case_not_searched_stopped_and_withheld(tmp_path):
    before = World(tmp_path / "before", []) if (tmp_path / "before").mkdir() is None else None
    assert before is not None
    first = before.service.answer(before.run_new(request(["documents"]))["task_id"])
    assert first["answer"].startswith("Nothing was searched") and first["not_searched"] and "withheld_sources" not in first
    cases = {"after:retrieved": ("The task was stopped", "task_stopped_no_answer"), "after:drafted": ("This answer is no longer available", "answer_withheld")}
    for boundary, (text, limitation) in cases.items():
        folder = tmp_path / boundary.replace(":", "_")
        folder.mkdir()
        w = _world(folder)
        record, _ = w.service.submit(request(["documents", "mail"]))
        w.faults.armed.add(boundary)
        with pytest.raises(SimulatedCrash):
            w.service.run(record["task_id"])
        w.restart()
        w.grants._grants.clear()  # every grant is revoked before the task resumes: no token at all
        final = w.service.run(record["task_id"])
        answer = w.service.answer(record["task_id"])
        assert (final["state"], final["terminal_reason"]) == ("failed", "denied")
        assert answer["answer"].startswith(text) and limitation in answer["limitations"], boundary
        assert "Nothing was searched" not in answer["answer"] and answer["not_searched"] == []
        assert {n["source_type"] for n in answer["withheld_sources"]} == {"documents", "mail"}


def _crash_revoke_restart(tmp_path, boundary: str):
    w = _world(tmp_path)
    record, _ = w.service.submit(request(["documents", "mail"]))
    w.faults.armed.add(boundary)
    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    step, data = w.store.checkpoint(record["task_id"])
    w.restart()
    w.grants._grants.clear()  # every grant is revoked before the task resumes
    final = w.service.run(record["task_id"])
    return w, record, (step, data), final, w.service.answer(record["task_id"])


@pytest.mark.criterion(9)
@pytest.mark.criterion(3)
@pytest.mark.parametrize("boundary", ["after:attempt", "mid:retrieved"])
def test_a_search_that_may_have_started_is_reported_as_attempted_never_as_nothing_searched_or_as_retrieved(tmp_path, boundary):
    # after:attempt: the marker is durable, the retriever was never called. mid:retrieved: the retriever returned, the passages were not saved.
    # From the stored state alone the two cannot be told apart, so both are 'attempted, retrieval not confirmed'.
    w, _record, (step, data), final, answer = _crash_revoke_restart(tmp_path, boundary)
    assert step == "policy_checked" and "passages" not in data and data["retrieval_started"] == ["documents", "mail"]  # the attempt is durable; no content is
    assert w.retriever.calls == (
        [] if boundary == "after:attempt" else ["documents", "mail"]
    )  # whether the search ran is not recoverable from the stored state
    assert (final["state"], final["terminal_reason"]) == ("failed", "denied")
    assert answer["answer"].startswith("The task was stopped") and answer["limitations"] == ["task_stopped_no_answer"]
    assert (
        "Nothing was searched" not in answer["answer"] and "no longer available" not in answer["answer"]
    )  # neither a certainty of 'not searched' nor a claimed draft
    assert answer["not_searched"] == [] and answer["withheld_sources"] == []  # nothing is claimed as definitely retrieved
    assert {n["source_type"] for n in answer["search_attempted_sources"]} == {"documents", "mail"}


@pytest.mark.criterion(9)
def test_the_marker_alone_proves_an_attempt_but_a_saved_retrieval_confirms_it(tmp_path):
    _, _, _, _, attempted_only = _crash_revoke_restart(tmp_path / "a", "after:attempt") if (tmp_path / "a").mkdir() is None else (None,) * 5
    _, _, _, _, confirmed = _crash_revoke_restart(tmp_path / "b", "after:retrieved") if (tmp_path / "b").mkdir() is None else (None,) * 5
    assert attempted_only["withheld_sources"] == [] and attempted_only["search_attempted_sources"]
    assert {n["source_type"] for n in confirmed["withheld_sources"]} == {"documents", "mail"} and confirmed[
        "search_attempted_sources"
    ] == []  # passages were durably recorded


@pytest.mark.criterion(9)
def test_a_crash_before_the_search_starts_is_still_nothing_searched(tmp_path):
    w = _world(tmp_path)
    record, _ = w.service.submit(request(["documents", "mail"]))
    w.faults.armed.add("before:retrieved")  # died before the retriever was ever called
    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    assert "retrieval_started" not in w.store.checkpoint(record["task_id"])[1] and w.retriever.calls == []
    w.restart()
    w.grants._grants.clear()
    w.service.run(record["task_id"])
    answer = w.service.answer(record["task_id"])
    assert answer["answer"].startswith("Nothing was searched") and "withheld_sources" not in answer
