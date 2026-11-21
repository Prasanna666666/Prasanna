"""G-O19: durable, owner-controlled, default-deny source designation, plus the OS-permission gate in front of every source adapter. Synthetic data only; the OS provider is a
deterministic fake (nothing here says anything about macOS/TCC behaviour)."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import KEY, Clock, World, request

from atlas_core import documents as docs_module
from atlas_core.access import GRANTED, MISSING, UNKNOWN, FakeOSPermissions, SourceAccess
from atlas_core.contracts import validate
from atlas_core.designation import (
    AnchorError,
    AnchorRecord,
    DesignationError,
    DesignationStore,
    InMemoryAnchor,
    Intent,
    OnboardingDecision,
    Pending,
    PurgePending,
    StoreCorrupt,
)
from atlas_core.documents import DocumentIndex, source_id_for
from atlas_core.policy import InMemoryGrants, PermissionRevoked, PolicyEngine

DOCS, MAIL = "documents", "mail"
SENTINEL = "DOCFILE-SENTINEL-7781"
NAME_SENTINEL = "confidential-sentinel-9035"
FACT = f"Invoice {SENTINEL}: the total due is 1250.50 euro."


class Env:
    """A designation store, a fake OS provider and the gate, on one clock, in a temp folder."""

    def __init__(self, folder: Path) -> None:
        self.folder, self.clock = folder, Clock()
        self.anchor = InMemoryAnchor()  # stands in for the platform secure-storage anchor that lives OUTSIDE the database
        self.store = DesignationStore(folder / "designation.db", KEY, self.clock, anchor=self.anchor)
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
        self.store = DesignationStore(self.folder / "designation.db", KEY, self.clock, anchor=self.anchor)
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
    fresh = DesignationStore(tmp_path / "fresh.db", KEY, env.clock, anchor=InMemoryAnchor())
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
    assert (
        touched.touches.count("read") == 1 and index.coverage()["searched"] == 0 and index.coverage()["total"] == 0
    )  # (the one call is the refused one: see the boundary tests)


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


# ---- review 6001015567, blocker 1: a restored whole-database snapshot must not resurrect withdrawn consent -----------------------------------------------
def _snapshot(env: Env, name: str) -> Path:
    env.store.close()  # a clean close leaves one complete database file (no side files)
    copy = env.folder / name
    shutil.copy(env.folder / "designation.db", copy)
    env.reopen()
    return copy


def _restore(env: Env, snapshot: Path) -> None:
    env.store.close()
    for suffix in ("-wal", "-shm", "-journal"):
        (env.folder / f"designation.db{suffix}").unlink(missing_ok=True)
    shutil.copy(snapshot, env.folder / "designation.db")
    env.reopen()


def test_restoring_an_older_complete_database_cannot_bring_back_withdrawn_consent(env):
    env.store.register_purge(DOCS, lambda: None)
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    enabled = _snapshot(env, "while_enabled.db")  # the complete database, with the source enabled
    assert env.access.permitted(DOCS) is True
    env.store.withdraw(DOCS, env.rid())
    assert env.access.permitted(DOCS) is False
    _restore(env, enabled)  # the old file is internally consistent: its rows, chain, head and state all match
    assert env.store.health() == "corrupt"
    assert env.store.grants_for(DOCS) == [] and env.access.permitted(DOCS) is False and env.store.lifecycle(DOCS) == "not_configured"
    with pytest.raises(StoreCorrupt):
        env.enable(DOCS)  # and nothing can be built on it


def test_a_restored_snapshot_is_caught_even_when_it_only_loses_the_last_change(env):
    env.store.register_purge(DOCS, lambda: None)
    env.enable(DOCS)
    before = _snapshot(env, "before_mail.db")
    env.enable(MAIL)
    _restore(env, before)
    assert env.store.health() == "corrupt" and env.store.grants_for(MAIL) == [] and env.store.grants_for(DOCS) == []


def test_an_anchor_that_cannot_be_read_fails_closed_and_recovers_when_it_can(env):
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    env.anchor.fail = True
    assert env.store.health() == "corrupt" and env.access.permitted(DOCS) is False
    env.anchor.fail = False
    assert env.store.health() == "ok" and env.access.permitted(DOCS) is True


def test_a_new_empty_database_under_an_older_anchor_is_refused_until_the_owner_starts_over(env, tmp_path):
    env.enable(DOCS)
    env.store.close()
    (tmp_path / "designation.db").unlink()  # the database was deleted or replaced by an empty one
    for suffix in ("-wal", "-shm"):
        (tmp_path / f"designation.db{suffix}").unlink(missing_ok=True)
    env.reopen()
    assert env.store.health() == "corrupt" and env.store.grants_for(DOCS) == []
    env.store.reset_anchor()  # deliberate: only possible on an empty store (nothing to resurrect)
    assert env.store.health() == "ok" and env.store.lifecycle(DOCS) == "not_configured"
    env.enable(DOCS)
    with pytest.raises(DesignationError):
        env.store.reset_anchor()  # never on a store that holds anything


# ---- review 6001015567, blocker 2: a withdrawal is one transaction --------------------------------------------------------------------------------------
def _consumed(env: Env, rid: str) -> bool:
    return env.store._conn.execute("SELECT 1 FROM requests WHERE request_id=?", (rid,)).fetchone() is not None


def test_a_crash_before_the_withdrawal_commits_leaves_the_source_enabled_and_the_request_retryable(env):
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    env.enable(DOCS)
    rid = env.rid()

    def die(name: str) -> None:
        raise RuntimeError(name)

    env.store.hook = die
    with pytest.raises(RuntimeError):
        env.store.withdraw(DOCS, rid)
    env.store.hook = None
    assert env.store.lifecycle(DOCS) == "enabled" and not _consumed(env, rid) and purged == []  # never 'enabled with the request consumed'
    assert env.store.withdraw(DOCS, rid) is True  # the same request can be retried and now takes effect
    assert env.store.lifecycle(DOCS) == "revoked" and purged == [DOCS]


def test_a_crash_right_after_the_withdrawal_commits_leaves_it_whole_and_the_purge_pending(env):
    env.enable(DOCS)
    rid = env.rid()

    def die(name: str) -> None:
        if name == "after_commit":
            raise RuntimeError(name)

    env.store.hook = die
    with pytest.raises(RuntimeError):
        env.store.withdraw(DOCS, rid)
    env.store.hook = None
    assert env.store.lifecycle(DOCS) == "revoked" and _consumed(env, rid)  # the revocation and the request id are committed together
    assert env.store.pending_purges() == [DOCS] and env.access.permitted(DOCS) is False  # revoked, with the purge still owed
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    assert env.store.run_pending_purges() == [] and purged == [DOCS]


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_a_withdrawal_never_consumes_its_request_without_revoking(env, point):
    env.enable(DOCS)
    rid = env.rid()

    def die(name: str) -> None:
        if name == point:
            raise RuntimeError(name)

    env.store.hook = die
    with pytest.raises(RuntimeError):
        env.store.withdraw(DOCS, rid)
    env.store.hook = None
    assert (env.store.lifecycle(DOCS) == "enabled") == (not _consumed(env, rid))  # consumed if and only if revoked


# ---- review 6001015567, blocker 3: the access check sits at the actual open, after every hook ------------------------------------------------------
class Opens:
    """Records every open of a directory or file below the folder (the real os.open calls), so 'no byte was read after revocation' is a count of zero."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
        self.calls: list[Any] = []
        real = os.open

        def recording(path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
            if dir_fd is not None or str(path).startswith(str(root)):
                self.calls.append(path)
            return real(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(docs_module.os, "open", recording)


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Env, DocumentIndex, Opens]:
    env = Env(tmp_path)
    index, _ = documents(tmp_path, env)
    (tmp_path / "docs" / "sub").mkdir()
    (tmp_path / "docs" / "sub" / "b.txt").write_text("sub budget text")
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    opens = Opens(monkeypatch, tmp_path / "docs")
    return env, index, opens


def test_a_scanner_cannot_be_built_without_an_access_guard(tmp_path):
    with pytest.raises(TypeError):
        docs_module.Scanner(tmp_path)  # type: ignore[call-arg]


@pytest.mark.parametrize("how", ["consent_withdrawn", "os_permission_lost"])
def test_access_ending_at_the_pre_read_boundary_means_zero_reads_and_no_indexed_text(tmp_path, monkeypatch, how):
    env, index, opens = _ready(tmp_path, monkeypatch)
    index.scan()
    assert env.access.permitted(DOCS)  # (also records that the platform permission was seen, so its loss below is a revocation)

    def end_access(name: str) -> None:
        if name != "doc:before":
            return
        if how == "consent_withdrawn":
            env.store.withdraw(DOCS, env.rid())
        else:
            env.os.set(DOCS, MISSING)

    index.hook = end_access
    opens.calls.clear()
    with pytest.raises(PermissionRevoked):
        index.run(10)
    assert opens.calls == []  # not one directory or file was opened after access ended, not even the document already in hand
    assert index.coverage()["searched"] == 0 and index.coverage()["total"] == 0  # and nothing was indexed (the revocation purged the index)
    assert env.store.lifecycle(DOCS) == "revoked"


@pytest.mark.parametrize("component", ["sub", "b.txt-open"])
def test_access_ending_inside_a_directory_walk_or_just_before_the_file_open_means_no_further_open(tmp_path, monkeypatch, component):
    env, index, opens = _ready(tmp_path, monkeypatch)
    index.scan()
    sid = source_id_for("sub/b.txt")
    index.run(10)
    assert index.get(sid) is not None  # the whole tree was readable
    fired: list[str] = []

    def end_access(when: str, part: str) -> None:
        wanted = ("before", "sub") if component == "sub" else ("after", "sub")
        if (when, part) == wanted and not fired:
            fired.append(part)
            env.store.withdraw(DOCS, env.rid())

    index.scanner.seam = end_access
    opens.calls.clear()
    if component == "sub":
        with pytest.raises(PermissionRevoked):
            index.scanner.walk()  # the walk reaches 'sub'; access ends at that very moment
    else:
        with pytest.raises(PermissionRevoked):
            index.scanner.read("sub/b.txt")  # the directory was opened; access ends before the file is
    assert fired and all("b.txt" not in str(c) for c in opens.calls)  # the file itself was never opened
    if component == "sub":
        assert len(opens.calls) <= 2  # at most the root and what was already open before the check (never 'sub' or anything below it)


def test_a_withdrawal_during_a_scan_stops_it_and_it_never_reports_complete(tmp_path, monkeypatch):
    env, index, opens = _ready(tmp_path, monkeypatch)
    index.hook = lambda name: env.store.withdraw(DOCS, env.rid()) if name == "scan:begin" else None  # right after the scan was started
    opens.calls.clear()
    with pytest.raises(PermissionRevoked):
        index.scan()
    assert opens.calls == [] and index.coverage()["complete"] is False


def test_access_ending_right_after_a_directory_was_opened_stops_it_being_listed(tmp_path, monkeypatch):
    env, index, _ = _ready(tmp_path, monkeypatch)
    listed: list[Any] = []
    real = os.scandir
    monkeypatch.setattr(docs_module.os, "scandir", lambda target: (listed.append(target), real(target))[1])
    fired: list[str] = []

    def end_access(when: str, part: str) -> None:
        if (when, part) == ("after", "sub") and not fired:
            fired.append(part)
            env.store.withdraw(DOCS, env.rid())

    index.scanner.seam = end_access
    with pytest.raises(PermissionRevoked):
        index.scanner.walk()
    assert fired and len(listed) == 1  # only the root was listed; 'sub' was opened but never listed once access had ended


class FlipAccess:
    """Permits the first N checks, then none: access ends between a caller's own check and the guarded read."""

    def __init__(self, allowed: int) -> None:
        self.allowed, self.n = allowed, 0

    def permitted(self, source_type: str) -> bool:
        self.n += 1
        return self.n <= self.allowed


def test_get_returns_nothing_rather_than_raising_when_access_ends_between_its_check_and_the_read(tmp_path):
    index = DocumentIndex(tmp_path / "i.db", KEY, tmp_path / "docs", DOCS, access=FlipAccess(10**6))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_text(FACT)
    index.scan()
    index.run(5)
    sid = source_id_for("a.txt")
    index._access = FlipAccess(1)  # get() is allowed once, then the guard in front of the file open is refused
    assert index.get(sid) is None


# ---- review 6001660112: the database is trusted only as far as the external anchor has recorded it (two-phase) ------------------------------------------
class ProcessDied(BaseException):
    """A simulated process death: not an ordinary error, so nothing in the store gets to clean up after it."""


def _die_at(env: Env, point: str) -> None:
    def hook(name: str) -> None:
        if name == point:
            raise ProcessDied(name)

    env.store.hook = hook


def _row_hash(env: Env, seq: int) -> str:
    return str(env.store._conn.execute("SELECT hash FROM audit WHERE seq=?", (seq,)).fetchone()[0])


def test_a_used_store_with_no_anchor_cannot_show_it_was_not_rolled_back(env):
    env.enable(DOCS)
    env.anchor.record = None  # the secure-storage item is gone
    assert env.store.health() == "corrupt" and env.store.grants_for(DOCS) == []


def test_an_anchor_for_the_same_sequence_with_another_head_is_a_rollback_or_fork(env):
    env.enable(DOCS)
    env.anchor.record = AnchorRecord(env.anchor.record.seq, "e" * 64)
    assert env.store.health() == "corrupt"


def test_a_database_that_holds_a_change_the_anchor_never_recorded_is_refused(env):
    env.enable(DOCS)
    env.enable(MAIL)
    env.anchor.record = AnchorRecord(1, _row_hash(env, 1))  # the anchor knows only the first change and has nothing pending
    assert env.store.health() == "corrupt" and env.store.grants_for(DOCS) == [] and env.store.grants_for(MAIL) == []


def test_a_pending_record_that_matches_neither_state_is_refused(env):
    env.enable(DOCS)
    env.enable(MAIL)
    env.anchor.record = AnchorRecord(1, _row_hash(env, 1), Pending(5, "f" * 64, None))  # the database is two changes in; the anchor expects a fifth
    assert env.store.health() == "corrupt" and env.store.grants_for(DOCS) == []


def test_the_anchor_contract_is_forward_only_and_two_phase():
    anchor = InMemoryAnchor()
    anchor.initialize(0, "0" * 64)
    anchor.initialize(9, "9" * 64)  # an existing record is never replaced by a new store's start
    assert anchor.read() == AnchorRecord(0, "0" * 64)
    with pytest.raises(AnchorError):
        anchor.commit(1, "a" * 64)  # nothing was prepared
    anchor.prepare(1, "a" * 64, None)
    with pytest.raises(AnchorError):
        anchor.prepare(2, "b" * 64, None)  # one unresolved change at a time
    with pytest.raises(AnchorError):
        anchor.commit(1, "c" * 64)  # the finished state must be the intended one
    anchor.commit(1, "a" * 64)
    with pytest.raises(AnchorError):
        anchor.prepare(1, "d" * 64, None)  # never backwards or sideways
    restriction = Intent(MAIL, "owner_withdrawn", "request-000001")
    anchor.prepare(2, "e" * 64, restriction)
    anchor.prepare(2, "f" * 64, restriction)  # the same restriction may be replayed in the same position (that is how it is completed)
    anchor.abort()
    assert anchor.read() == AnchorRecord(1, "a" * 64)


@pytest.mark.parametrize("change", ["enable", "withdrawal"])
def test_a_committed_change_the_anchor_could_not_record_is_not_trusted_for_reads_or_writes(env, change):
    env.os.set(DOCS, GRANTED)
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    if change == "withdrawal":
        env.enable(DOCS)
        assert env.access.permitted(DOCS) is True
    env.anchor.fail_commit = True  # the platform store refuses to record the FINISH of the change
    if change == "enable":
        env.enable(DOCS)
    else:
        assert env.store.withdraw(DOCS, env.rid()) is True and purged == [DOCS]  # the withdrawal committed and its purge still ran
    assert env.store.grants_for(DOCS) == [] and env.access.permitted(DOCS) is False and env.store.lifecycle(DOCS) == "not_configured"  # nothing is trusted
    assert env.store.health() == "corrupt"
    with pytest.raises(StoreCorrupt):
        env.enable(MAIL)  # and nothing can be built on it
    env.anchor.fail_commit = False  # reconciled: now (and only now) the committed state is trusted
    assert env.store.health() == "ok"
    assert env.store.lifecycle(DOCS) == ("enabled" if change == "enable" else "revoked")
    assert env.access.permitted(DOCS) is (change == "enable")


@pytest.mark.parametrize("change", ["enable", "withdrawal"])
def test_a_change_the_anchor_cannot_record_in_advance_is_not_made_at_all(env, change):
    env.enable(DOCS)
    rid = env.rid()
    env.anchor.fail_prepare = True
    with pytest.raises(OSError):
        env.enable(MAIL) if change == "enable" else env.store.withdraw(DOCS, rid)
    env.anchor.fail_prepare = False
    assert env.store.health() == "ok" and env.store.lifecycle(MAIL) == "not_configured" and env.store.lifecycle(DOCS) == "enabled"
    assert not _consumed(env, rid) and len(env.store.audit_log()) == 1


def test_dying_right_after_the_commit_is_finalised_at_the_next_start(env):
    _die_at(env, "after_commit")
    with pytest.raises(ProcessDied):
        env.enable(DOCS)
    env.store.hook = None
    env.reopen()
    assert env.store.health() == "ok" and env.store.lifecycle(DOCS) == "enabled" and env.anchor.record.pending is None


def test_dying_before_an_enable_commits_leaves_nothing_granted_and_a_clean_store(env):
    _die_at(env, "before_commit")
    with pytest.raises(ProcessDied):
        env.enable(DOCS)
    env.store.hook = None
    assert env.anchor.record.pending is not None  # the intent was recorded before the commit
    env.reopen()
    assert env.store.health() == "ok" and env.store.lifecycle(DOCS) == "not_configured" and env.anchor.record.pending is None
    env.enable(DOCS)  # and the owner can simply enable again
    assert env.store.lifecycle(DOCS) == "enabled"


def test_dying_before_a_withdrawal_commits_still_completes_the_withdrawal_at_the_next_start(env):
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    env.enable(DOCS)
    rid = env.rid()
    _die_at(env, "before_commit")
    with pytest.raises(ProcessDied):
        env.store.withdraw(DOCS, rid)
    env.store.hook = None
    env.reopen()
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    assert env.store.lifecycle(DOCS) == "revoked" and env.store.health() == "ok"  # a restriction recorded as intended is never lost
    assert _consumed(env, rid) and purged == [DOCS] and env.store.pending_purges() == []
    with pytest.raises(DesignationError, match="replayed"):
        env.store.withdraw(DOCS, rid)


@pytest.mark.parametrize("anchor_unfinished", ["commit_refused", "process_died"])
def test_restoring_the_snapshot_from_before_an_unfinished_withdrawal_cannot_resurrect_consent(env, anchor_unfinished):
    purged: list[str] = []
    env.store.register_purge(DOCS, lambda: purged.append(DOCS))
    env.enable(DOCS)
    env.os.set(DOCS, GRANTED)
    snapshot = _snapshot(env, "while_enabled.db")
    assert env.access.permitted(DOCS) is True
    if anchor_unfinished == "commit_refused":
        env.anchor.fail_commit = True
        env.store.withdraw(DOCS, env.rid())
    else:
        _die_at(env, "after_commit")
        with pytest.raises(ProcessDied):
            env.store.withdraw(DOCS, env.rid())
        env.store.hook = None
    _restore(env, snapshot)  # the anchor holds the withdrawal as pending; the restored database is one change behind it
    if anchor_unfinished == "commit_refused":
        assert env.store.grants_for(DOCS) == [] and env.access.permitted(DOCS) is False  # completing it cannot be recorded yet: nothing is trusted
        env.anchor.fail_commit = False
    assert env.store.health() == "ok"
    assert env.store.lifecycle(DOCS) == "revoked" and env.access.permitted(DOCS) is False  # the withdrawal was applied to the restored database
    assert env.store.grants_for(DOCS)[-1]["revoked"] is True


def test_restoring_the_snapshot_from_before_an_unfinished_enable_grants_nothing(env):
    env.enable(DOCS)
    snapshot = _snapshot(env, "before_mail.db")
    env.anchor.fail_commit = True
    env.enable(MAIL)
    _restore(env, snapshot)
    env.anchor.fail_commit = False
    assert env.store.health() == "ok" and env.store.lifecycle(MAIL) == "not_configured" and env.store.grants_for(MAIL) == []  # an unrealised enable is dropped
    assert env.store.lifecycle(DOCS) == "enabled"


@pytest.mark.parametrize("cause", ["os_permission_lost", "grant_expired"])
def test_dying_before_an_automatic_revocation_commits_still_completes_it_at_the_next_start(env, cause):
    env.enable(DOCS, expires=env.clock() + timedelta(seconds=60) if cause == "grant_expired" else None)
    env.os.set(DOCS, GRANTED)
    assert env.access.permitted(DOCS) is True  # (the permission is seen, so its loss below is a revocation)
    if cause == "os_permission_lost":
        env.os.set(DOCS, MISSING)
    else:
        env.clock.advance(61)
    _die_at(env, "before_commit")
    with pytest.raises(ProcessDied):
        env.access.permitted(DOCS)
    env.store.hook = None
    env.reopen()
    assert env.store.lifecycle(DOCS) == "revoked" and env.store.health() == "ok"
    assert env.store.audit_log()[-1]["reason"] == cause
