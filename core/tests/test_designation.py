"""G-O19: durable, owner-controlled, default-deny source designation, plus the OS-permission gate in front of every source adapter. Synthetic data only; the OS provider is a
deterministic fake (nothing here says anything about macOS/TCC behaviour)."""

from __future__ import annotations

import contextlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import KEY, Clock, World, request

from atlas_core.access import GRANTED, MISSING, UNKNOWN, FakeOSPermissions, SourceAccess
from atlas_core.contracts import validate
from atlas_core.designation import DesignationError, DesignationStore, OnboardingDecision, PurgePending, StoreCorrupt
from atlas_core.documents import DocumentIndex
from atlas_core.policy import InMemoryGrants, PermissionRevoked, PolicyEngine

DOCS, MAIL = "documents", "mail"
SENTINEL = "DOCFILE-SENTINEL-7781"
NAME_SENTINEL = "confidential-sentinel-9035"
FACT = f"Invoice {SENTINEL}: the total due is 1250.50 euro."


class Env:
    """A designation store, a fake OS provider and the gate, on one clock, in a temp folder."""

    def __init__(self, folder: Path) -> None:
        self.folder, self.clock = folder, Clock()
        self.store = DesignationStore(folder / "designation.db", KEY, self.clock)
        self.os = FakeOSPermissions(self.clock)
        self.access = SourceAccess(self.store, self.os, self.clock)
        self.n = 0

    def rid(self) -> str:
        self.n += 1
        return f"request-{self.n:06d}"

    def enable(self, *types: str, expires: Any = None) -> dict[str, list[str]]:
        return self.store.apply(OnboardingDecision(enable=frozenset(types), expires_at=expires), self.rid())

    def decision(self, source_type: str) -> tuple[dict[str, Any], Any]:
        return PolicyEngine(self.access).decide([source_type], self.clock())

    def reopen(self) -> None:
        self.store.close()
        self.store = DesignationStore(self.folder / "designation.db", KEY, self.clock)
        self.access = SourceAccess(self.store, self.os, self.clock)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


# ---- default deny and what can be designated -----------------------------------------------------------------------------------------------------
def test_a_fresh_install_enables_nothing_and_everything_is_denied(env):
    assert env.store.designable() == [DOCS, MAIL]  # attachments, Finance and Health are never designated here
    assert [env.store.lifecycle(t) for t in (DOCS, MAIL)] == ["not_configured", "not_configured"]
    assert env.store.grants_for(DOCS) == [] and env.access.permitted(DOCS) is False
    decision, token = env.decision(DOCS)
    assert token is None and decision["reason_code"] == "no_grant"
    state = env.access.consent_state()
    assert state == {"grants": [], "sources": [{"source_type": DOCS, "os_access": UNKNOWN}, {"source_type": MAIL, "os_access": UNKNOWN}]}
    validate("ConsentState", state, version="1.1")  # the owner-facing shape is the 1.1 shape (not served)


@pytest.mark.parametrize("bad", [frozenset({"finance"}), frozenset({"health"}), frozenset({"mail_attachment"}), frozenset({"nothing_like_it"}), frozenset()])
def test_only_designable_source_types_can_be_decided_and_a_refusal_changes_nothing(env, bad):
    with pytest.raises(DesignationError):
        env.store.apply(OnboardingDecision(enable=bad | {DOCS} if bad else bad), env.rid())
    assert env.store.lifecycle(DOCS) == "not_configured" and env.store.audit_log() == []  # the valid part of a refused decision was not applied either


def test_enabling_and_declining_the_same_type_is_refused(env):
    with pytest.raises(DesignationError):
        env.store.apply(OnboardingDecision(enable=frozenset({DOCS}), decline=frozenset({DOCS})), env.rid())
    assert env.store.audit_log() == []


@pytest.mark.parametrize(("enabled", "declined"), [({DOCS}, {MAIL}), ({MAIL}, {DOCS}), (set(), {DOCS, MAIL}), ({DOCS}, set()), ({MAIL}, set())])
def test_each_source_type_is_decided_on_its_own_and_one_never_enables_the_other(env, enabled, declined):
    env.store.apply(OnboardingDecision(enable=frozenset(enabled), decline=frozenset(declined)), env.rid())
    env.os.set(DOCS, GRANTED)
    env.os.set(MAIL, GRANTED)
    for source_type in (DOCS, MAIL):
        decision, token = env.decision(source_type)
        if source_type in enabled:
            assert token is not None and env.store.lifecycle(source_type) == "enabled"
        else:
            assert token is None and env.store.lifecycle(source_type) == ("declined" if source_type in declined else "not_configured")
            assert decision["reason_code"] == "no_grant"
    assert not enabled & declined


def test_the_get_started_consent_request_shape_enables_only_what_it_lists(env):
    request_shape = {"sources": [DOCS]}
    validate("ConsentRequest", request_shape, version="1.1")
    env.store.apply(OnboardingDecision.from_consent_request(request_shape), env.rid())
    assert (env.store.lifecycle(DOCS), env.store.lifecycle(MAIL)) == ("enabled", "not_configured")


def test_an_enabled_source_is_not_declined_it_is_withdrawn_and_a_declined_one_can_be_enabled_later(env):
    env.store.apply(OnboardingDecision(decline=frozenset({MAIL})), env.rid())
    env.enable(MAIL)  # declined -> enabled
    assert env.store.lifecycle(MAIL) == "enabled"
    with pytest.raises(DesignationError):
        env.store.apply(OnboardingDecision(decline=frozenset({MAIL})), env.rid())
    assert env.store.lifecycle(MAIL) == "enabled"


def test_enabling_twice_keeps_the_same_grant_and_does_not_issue_a_second(env):
    env.enable(DOCS)
    first = env.store.grants_for(DOCS)
    assert env.enable(DOCS) == {"enabled": [], "declined": [], "unchanged": [DOCS]}
    assert env.store.grants_for(DOCS) == first and len(first) == 1


# ---- the grant is the existing SourceGrant, with identity, ceiling, purpose, expiry ---------------------------------------------------------------------
def test_a_designation_grant_is_a_valid_source_grant_with_the_types_ceiling_and_a_unique_identity(env):
    env.enable(DOCS, MAIL)
    docs, mail = env.store.grants_for(DOCS)[0], env.store.grants_for(MAIL)[0]
    for grant in (docs, mail):
        validate("SourceGrant", grant)
        assert grant["designated_by"] == "owner" and grant["purpose"] == "answer_question" and grant["revoked"] is False
    assert (docs["max_sensitivity"], mail["max_sensitivity"]) == ("medium", "high")  # the policy's own sensitivity for each type, never above it
    assert docs["grant_id"] != mail["grant_id"]


def test_policy_decisions_match_the_in_memory_grants_the_earlier_fixtures_use(env):
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    legacy = InMemoryGrants([{**env.store.grants_for(DOCS)[0], "grant_id": "legacy-grant-0001"}])
    ours, _ = env.decision(DOCS)
    theirs, _ = PolicyEngine(legacy).decide([DOCS], env.clock())
    assert {k: v for k, v in ours.items() if k != "grant_ids"} == {k: v for k, v in theirs.items() if k != "grant_ids"}
    for other in (MAIL, "finance", "mail_attachment"):  # and the denials agree too
        assert env.decision(other)[0]["denied"] == PolicyEngine(legacy).decide([other], env.clock())[0]["denied"]


# ---- the OS permission: positive, current evidence, never a cached consent ---------------------------------------------------------------------------
def test_consent_alone_is_not_enough_the_platform_permission_must_be_evidenced_now(env):
    env.enable(DOCS)
    assert env.access.permitted(DOCS) is False and env.decision(DOCS)[0]["reason_code"] == "no_grant"  # the owner said yes; the platform has not
    env.os.set(DOCS, GRANTED)
    assert env.access.permitted(DOCS) is True
    env.os.set(DOCS, UNKNOWN)
    assert env.access.permitted(DOCS) is False  # asked again on every check: yesterday's answer is not today's
    assert env.store.lifecycle(DOCS) == "enabled"  # a platform that has not decided yet does not undo the owner's consent


@pytest.mark.parametrize("state", [MISSING, UNKNOWN])
def test_a_permission_that_was_never_granted_denies_without_revoking_the_consent(env, state):
    env.enable(DOCS)
    env.os.set(DOCS, state)
    assert env.access.permitted(DOCS) is False and env.store.lifecycle(DOCS) == "enabled"
    assert env.access.consent_state()["sources"][0]["os_access"] == state


def test_evidence_that_is_stale_future_dated_about_another_type_or_from_a_failing_provider_is_no_evidence(env):
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    assert env.access.permitted(DOCS) is True
    env.os.stale_by = timedelta(seconds=120)
    assert env.access.permitted(DOCS) is False  # an old observation
    env.os.stale_by = timedelta(seconds=-120)
    assert env.access.permitted(DOCS) is False  # one dated in the future
    env.os.stale_by = None
    env.os.fail = True
    assert env.access.permitted(DOCS) is False  # a provider that errors
    env.os.fail = False
    assert env.access.permitted(DOCS) is True
    assert env.store.lifecycle(DOCS) == "enabled"  # none of those is a revocation: they only deny the check they happened in


def test_evidence_for_another_source_type_does_not_count(env):
    env.enable(DOCS)
    real = env.os.current
    env.os.current = lambda source_type: real(MAIL)  # type: ignore[method-assign]  (a provider that answers about the wrong type)
    env.os.set(MAIL, GRANTED)
    assert env.access.permitted(DOCS) is False


def test_the_platform_taking_a_granted_permission_back_revokes_the_grant_and_purges(env):
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    old = env.store.grants_for(DOCS)[0]["grant_id"]
    assert env.access.permitted(DOCS) is True
    env.os.set(DOCS, MISSING)  # revoked in System Settings
    assert env.access.permitted(DOCS) is False
    assert env.store.lifecycle(DOCS) == "revoked" and purged == [DOCS]
    assert [(r["from_state"], r["to_state"], r["reason"]) for r in env.store.audit_log()][-1] == ("enabled", "revoked", "os_permission_lost")
    env.os.set(DOCS, GRANTED)  # the permission comes back, but the old grant does not
    assert env.access.permitted(DOCS) is False and env.decision(DOCS)[0]["reason_code"] == "grant_revoked"
    env.enable(DOCS)  # the owner enables again: a NEW grant identity
    assert env.access.permitted(DOCS) is True and env.store.grants_for(DOCS)[-1]["grant_id"] != old


# ---- withdrawal, replay, revoke and regrant ---------------------------------------------------------------------------------------------------------
def test_withdrawing_consent_revokes_at_once_purges_and_a_regrant_is_a_new_identity(env):
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    _, token = env.decision(DOCS)
    assert token is not None
    env.store.withdraw(DOCS, env.rid())
    assert env.access.permitted(DOCS) is False and purged == [DOCS] and env.store.pending_purges() == []
    env.enable(DOCS)
    assert env.access.permitted(DOCS) is True
    current, denied = PolicyEngine(env.access).revalidate(token, env.clock())
    assert current == frozenset() and denied == [
        {"source_type": DOCS, "reason_code": "grant_revoked"}
    ]  # the old authority does not carry over to the new grant


def test_a_request_id_is_single_use_so_an_old_enable_cannot_be_replayed_after_a_withdrawal(env):
    rid = env.rid()
    env.store.apply(OnboardingDecision(enable=frozenset({DOCS})), rid)
    env.store.withdraw(DOCS, env.rid())
    with pytest.raises(DesignationError, match="replayed"):
        env.store.apply(OnboardingDecision(enable=frozenset({DOCS})), rid)
    assert env.store.lifecycle(DOCS) == "revoked"
    for bad in ("short", "x" * 65):
        with pytest.raises(DesignationError):
            env.store.apply(OnboardingDecision(enable=frozenset({DOCS})), bad)


def test_a_grant_expires_is_revoked_and_its_data_purged(env):
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    env.enable(DOCS, expires=env.clock() + timedelta(seconds=60))
    env.os.set(DOCS, GRANTED)
    assert env.access.permitted(DOCS) is True
    env.clock.advance(61)
    assert env.access.permitted(DOCS) is False and purged == [DOCS]
    assert env.store.audit_log()[-1]["reason"] == "grant_expired" and env.store.lifecycle(DOCS) == "revoked"


def test_a_failed_purge_leaves_the_source_revoked_blocks_a_new_grant_and_is_retried(env):
    env.enable(DOCS)
    broken = {"fail": True}

    def purge() -> None:
        if broken["fail"]:
            raise OSError("disk error")

    env.store.register_purge(DOCS, purge)
    env.store.withdraw(DOCS, env.rid())
    assert env.store.lifecycle(DOCS) == "revoked" and env.store.pending_purges() == [DOCS]
    with pytest.raises(PurgePending):
        env.enable(DOCS)  # stale derived data must never be served under a new grant
    assert env.store.run_pending_purges() == [DOCS]  # still failing
    broken["fail"] = False
    assert env.store.run_pending_purges() == []
    env.enable(DOCS)
    assert env.store.lifecycle(DOCS) == "enabled"


def test_a_crash_between_revocation_and_purge_is_finished_at_the_next_start(env):
    env.enable(DOCS)
    env.store.withdraw(DOCS, env.rid())  # no purge function was registered yet (the process died before it ran): the purge stays pending
    assert env.store.pending_purges() == [DOCS]
    purged: list[str] = []
    env.reopen()
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    assert env.store.run_pending_purges() == [] and purged == [DOCS]


# ---- durability: restart, atomicity, corruption (all fail closed) ---------------------------------------------------------------------------------------
def test_the_designation_survives_a_restart_and_a_missing_file_means_nothing_is_enabled(env, tmp_path):
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    assert env.access.permitted(DOCS) is True
    env.reopen()
    assert env.store.lifecycle(DOCS) == "enabled" and env.access.permitted(DOCS) is True
    fresh = DesignationStore(tmp_path / "fresh.db", KEY, env.clock)
    assert fresh.lifecycle(DOCS) == "not_configured" and fresh.grants_for(DOCS) == []


def test_a_crash_inside_a_change_leaves_neither_the_change_nor_its_audit_row_nor_the_used_request_id(env):
    def die(name: str) -> None:
        raise RuntimeError(name)

    env.store.hook = die
    rid = env.rid()
    with pytest.raises(RuntimeError):
        env.store.apply(OnboardingDecision(enable=frozenset({DOCS})), rid)
    env.store.hook = None
    assert env.store.lifecycle(DOCS) == "not_configured" and env.store.audit_log() == [] and env.store.health() == "ok"
    env.store.apply(OnboardingDecision(enable=frozenset({DOCS})), rid)  # the same request can still be made: nothing was consumed
    assert env.store.lifecycle(DOCS) == "enabled"


TAMPERS = {
    "audit_state_changed": "UPDATE audit SET to_state='declined' WHERE seq=1",
    "audit_row_removed": "DELETE FROM audit WHERE seq=2",
    "grant_ceiling_raised": "UPDATE grants SET max_sensitivity='restricted'",
    "grant_revoked_flag_cleared": "UPDATE grants SET revoked=0",
    "state_forced": "UPDATE state SET state='declined'",
    "grant_expiry_changed": "UPDATE grants SET expires_at='2099-01-01T00:00:00+00:00'",
    "grant_inserted": "INSERT INTO grants (grant_id, source_type, max_sensitivity, purpose, issued_at) VALUES ('gforged0000000001','mail','high','answer_question','2026-01-01T00:00:00+00:00')",
    "audit_reason_rewritten": "UPDATE audit SET reason='something_else' WHERE seq=1",
    "audit_time_rewritten": "UPDATE audit SET at='2020-01-01T00:00:00+00:00' WHERE seq=1",
    "audit_prev_hash_rewritten": "UPDATE audit SET prev_hash='" + "1" * 64 + "' WHERE seq=2",
    "schema_downgraded": "UPDATE meta SET value='0' WHERE key='schema'",
    "head_rewound": "UPDATE meta SET value='0:" + "0" * 64 + "' WHERE key='head'",
}


@pytest.mark.parametrize("name", sorted(TAMPERS))
def test_a_corrupt_downgraded_or_tampered_record_withholds_every_grant_and_refuses_changes(env, name):
    env.store.register_purge(DOCS, lambda: None)
    env.enable(DOCS)
    env.store.withdraw(DOCS, env.rid())  # a revoked grant, so 'revoked flag cleared' is detectable too
    env.enable(DOCS, MAIL)
    env.os.set(DOCS, GRANTED)
    assert env.access.permitted(DOCS) is True
    env.store._conn.execute(TAMPERS[name])
    assert env.store.health() == "corrupt"
    assert env.store.grants_for(DOCS) == [] and env.store.grants_for(MAIL) == [] and env.access.permitted(DOCS) is False
    assert env.store.lifecycle(DOCS) == "not_configured"
    with pytest.raises(StoreCorrupt):
        env.enable(MAIL)
    with pytest.raises(StoreCorrupt):
        env.store.withdraw(DOCS, env.rid())


def test_an_unreadable_record_is_corrupt_not_a_crash(env):
    env.enable(DOCS)
    env.store._conn.execute("DROP TABLE audit")
    assert env.store.health() == "corrupt" and env.store.grants_for(DOCS) == []


def test_the_audit_trail_is_content_free(env, tmp_path):
    root = tmp_path / NAME_SENTINEL
    root.mkdir()
    (root / "a.txt").write_text(FACT)
    env.enable(DOCS, MAIL)
    env.store.withdraw(MAIL, env.rid())
    dump = json.dumps([env.store.audit_log(), env.access.consent_state()])
    assert SENTINEL not in dump and NAME_SENTINEL not in dump and str(tmp_path) not in dump
    assert {k for row in env.store.audit_log() for k in row} == {"seq", "at", "source_type", "from_state", "to_state", "grant_id", "reason"}


# ---- no source byte is touched before BOTH gates pass; revocation fails closed at every boundary ---------------------------------------------------------
class TouchCounter:
    """Counts every attempt to enumerate or read the folder (the scanner), to prove nothing was touched."""

    def __init__(self, index: DocumentIndex) -> None:
        self.touches: list[str] = []
        walk, read = index.scanner.walk, index.scanner.read
        index.scanner.walk = lambda: (self.touches.append("walk"), walk())[1]  # type: ignore[method-assign]
        index.scanner.read = lambda rel: (self.touches.append("read"), read(rel))[1]  # type: ignore[method-assign]


def documents(tmp_path: Path, env: Env) -> tuple[DocumentIndex, TouchCounter]:
    root = tmp_path / "docs"
    root.mkdir(exist_ok=True)
    (root / "a.txt").write_text(FACT)
    index = DocumentIndex(tmp_path / "index.db", KEY, root, DOCS, access=env.access)
    env.store.register_purge(DOCS, index.purge)
    return index, TouchCounter(index)


@pytest.mark.parametrize("consent", [False, True])
@pytest.mark.parametrize("os_state", [GRANTED, MISSING, UNKNOWN])
def test_no_folder_byte_is_touched_unless_consent_and_the_platform_permission_are_both_current(tmp_path, consent, os_state):
    env = Env(tmp_path)
    index, touched = documents(tmp_path, env)
    if consent:
        env.enable(DOCS)
    env.os.set(DOCS, os_state)
    both = consent and os_state == GRANTED
    for step in (index.scan, lambda: index.run(5), lambda: list(index.search(DOCS, "invoice")), lambda: index.get("d" + "0" * 24)):
        if both:
            continue
        with contextlib.suppress(PermissionRevoked):
            step()
    if both:
        index.scan()
        index.run(5)
        assert len(list(index.search(DOCS, "invoice"))) == 1 and touched.touches
    else:
        assert touched.touches == [] and index.coverage()["total"] == 0  # not even the folder listing was attempted


def test_search_raises_revoked_and_get_returns_nothing_the_moment_access_ends(tmp_path):
    env = Env(tmp_path)
    index, touched = documents(tmp_path, env)
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    index.scan()
    index.run(5)
    (p,) = index.search(DOCS, "invoice")
    env.store.withdraw(DOCS, env.rid())
    touched.touches.clear()
    with pytest.raises(PermissionRevoked):
        list(index.search(DOCS, "invoice"))
    assert index.get(p["evidence"]["source_id"]) is None and touched.touches == []
    assert index.coverage()["total"] == 0  # and the index was purged by the revocation


def test_access_lost_between_two_documents_stops_before_the_next_one(tmp_path):
    env = Env(tmp_path)
    index, touched = documents(tmp_path, env)
    for i in range(3):
        (tmp_path / "docs" / f"f{i}.txt").write_text(f"budget item {i}")
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    index.scan()
    index.hook = lambda name: env.store.withdraw(DOCS, env.rid()) if name == "doc:before" and env.store.lifecycle(DOCS) == "enabled" else None
    with pytest.raises(PermissionRevoked):
        index.run(10)
    reads = touched.touches.count("read")
    assert reads <= 1  # at most the document already in hand; none after the withdrawal
    assert index.coverage()["searched"] == 0 and index.coverage()["total"] == 0


def world(tmp_path: Path, env: Env) -> tuple[World, DocumentIndex]:
    index, _ = documents(tmp_path, env)
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    index.scan()
    index.run(10)
    (tmp_path / "w").mkdir()
    w = World(tmp_path / "w", [])
    w.grants = env.access  # type: ignore[assignment]  (the policy engine reads grants from the gate)
    w.sources, w.retriever = index, index
    w.model.answer_text, w.model.quote = "The total due is 1250.50 euro.", "1250.50"
    w.service = w._service()
    return w, index


def run_task(w: World) -> dict[str, Any]:
    return w.run_new(request([DOCS], objective="what is the total due invoice"))


def test_the_whole_path_answers_only_while_consent_and_the_platform_permission_are_current(tmp_path):
    env = Env(tmp_path)
    w, _ = world(tmp_path, env)
    record = run_task(w)
    assert record["state"] == "completed" and "1250.50" in w.service.answer(record["task_id"])["answer"]
    env.os.set(DOCS, MISSING)  # the platform takes the permission back
    again = w.run_new(request([DOCS], objective="what is the total due invoice", key="idem-key-0002"))
    assert again["state"] == "failed" and again["terminal_reason"] == "denied" and len(w.model.calls) == 1
    served = json.dumps([w.service.answer(record["task_id"]), w.service.events_after(record["task_id"], 0)])
    assert "1250.50" not in served and SENTINEL not in served  # and the earlier answer is no longer served either


@pytest.mark.parametrize("moment", ["search", "model"])
def test_consent_withdrawn_during_a_task_stops_the_next_read_and_the_model(tmp_path, moment):
    env = Env(tmp_path)
    w, index = world(tmp_path, env)
    withdraw = lambda: env.store.withdraw(DOCS, env.rid())  # noqa: E731
    if moment == "search":
        real = index.search
        index.search = lambda t, q: (withdraw(), real(t, q))[1]  # type: ignore[method-assign]  (withdrawn just as the source is about to be read)
    else:
        w.model.on_call = withdraw  # withdrawn while the model is answering
    record = run_task(w)
    if moment == "search":
        assert (record["state"], record["terminal_reason"]) == (
            "failed",
            "denied",
        ) and w.model.calls == []  # stopped before the next read: the model never saw anything
    else:
        assert record["state"] == "failed" and len(w.model.calls) == 1  # withdrawn while answering: the draft cannot be verified against the purged source
    answer = w.service.answer(record["task_id"])
    served = json.dumps([answer, w.service.events_after(record["task_id"], 0)])
    assert "1250.50" not in served and SENTINEL not in served and answer["citations"] == []
    assert index.coverage()["total"] == 0  # the derived data went with the grant


def test_a_revoke_and_regrant_cannot_resurrect_the_purged_index_or_old_checkpoint_data(tmp_path):
    env = Env(tmp_path)
    w, index = world(tmp_path, env)
    record, _ = w.service.submit(request([DOCS], objective="what is the total due invoice", max_retries=5))
    w.faults.armed.add("after:retrieved")
    from atlas_core.service import SimulatedCrash

    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    w.faults.armed.discard("after:retrieved")
    env.store.withdraw(DOCS, env.rid())
    env.enable(DOCS)  # the owner enables again: a new identity, an empty index
    w.restart()
    w.service.run(record["task_id"])
    final = w.store.record(record["task_id"])
    assert (final["state"], final["terminal_reason"]) == ("failed", "denied") and w.model.calls == []
    assert list(index.search(DOCS, "invoice")) == [] and index.coverage()["total"] == 0  # until a new scan under the new grant


def test_a_platform_permission_that_is_not_current_blocks_reading_even_while_the_index_still_holds_rows(tmp_path):
    env = Env(tmp_path)
    index, touched = documents(tmp_path, env)
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    index.scan()
    index.run(5)
    (p,) = index.search(DOCS, "invoice")
    env.os.set(DOCS, UNKNOWN)  # not evidenced now (and not a loss): nothing is purged, but nothing may be read
    touched.touches.clear()
    assert index.get(p["evidence"]["source_id"]) is None and touched.touches == []
    with pytest.raises(PermissionRevoked):
        list(index.search(DOCS, "invoice"))
    assert index.coverage()["searched"] == 1  # the rows are still there (consent was not withdrawn)
    env.os.set(DOCS, GRANTED)
    assert index.get(p["evidence"]["source_id"]) is not None  # and they are usable again as soon as the platform evidences access
