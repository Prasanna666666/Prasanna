"""Stage 8 (Core side): a device's offline queue is applied once, in order; conflicts are reported not overwritten; a revoked device or a forbidden operation changes nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import KEY
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.actions import ActionGateway
from atlas_core.identity import ClientRegistry
from atlas_core.record_actions import register_record_actions
from atlas_core.recordstore import RecordStore, StoreError
from atlas_core.sync import MAX_OPS, OfflineQueue, QueuedOp, SyncService, cache_policy

pytestmark = pytest.mark.criterion(14)


class Rig:
    def __init__(self, tmp):
        self.store = RecordStore(tmp / "edits.db", KEY + "e", frozenset({"calendar", "contacts", "notes"}))
        self.registry = ClientRegistry()
        self.registry.register("phone-0001", Ed25519PrivateKey.generate().public_key())
        self.restart()

    def restart(self):
        """A restart of the Core: a new gateway and a new sync service (their memory of op ids is gone); the store and the registry are durable."""
        self.gateway = ActionGateway()
        register_record_actions(self.gateway, self.store, lambda p: {}, lambda rid: None)
        self.sync = SyncService(self.gateway, self.registry, self.version)

    def version(self, record_id):
        try:
            return self.store.get(record_id, include_deleted=True).version
        except StoreError:
            return None


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    yield r
    r.store.close()


def note(rid, text="x"):
    return {"id": rid, "date": "2026-10-18T00:00:00+00:00", "title": f"Note {rid}", "fields": {"text": text}}


def test_an_offline_queue_is_applied_in_order_and_reported_per_operation(rig):
    queue = OfflineQueue()
    queue.add("op-1", "notes.create", note("n1", "first"))
    queue.add("op-2", "notes.edit", {"id": "n1", "expected_version": 1, "fields": {"text": "second"}})
    queue.add("op-3", "notes.edit", {"id": "n1", "expected_version": 2, "fields": {"text": "third"}})
    results = rig.sync.apply("phone-0001", queue.ops)
    assert [(r.op_id, r.status) for r in results] == [("op-1", "applied"), ("op-2", "applied"), ("op-3", "applied")] and results[-1].current_version == 3
    assert rig.store.get("n1").record.fields["text"] == "third"


def test_replaying_the_queue_changes_nothing_even_after_a_restart_of_the_core(rig):
    queue = OfflineQueue()
    queue.add("op-1", "notes.create", note("n1"))
    queue.add("op-2", "notes.edit", {"id": "n1", "expected_version": 1, "fields": {"text": "edited"}})
    rig.sync.apply("phone-0001", queue.ops)
    again = rig.sync.apply("phone-0001", queue.ops)
    assert [r.status for r in again] == ["duplicate", "duplicate"] and rig.store.get("n1").version == 2
    rig.restart()  # the Core restarts: its memory of op ids is gone, the versions are not
    restarted = rig.sync.apply("phone-0001", queue.ops)
    assert (
        [r.status for r in restarted] == ["conflict", "conflict"] and rig.store.get("n1").version == 2 and rig.store.get("n1").record.fields["text"] == "edited"
    )


def test_an_edit_made_against_an_old_version_is_a_conflict_that_never_overwrites(rig):
    rig.sync.apply("phone-0001", [QueuedOp("op-1", "notes.create", note("n1", "from phone"))])
    rig.gateway.propose(
        "notes.edit", {"id": "n1", "expected_version": 1, "fields": {"text": "edited on the Mac"}}, origin="owner_request", idempotency_key="mac-1"
    )
    stale = rig.sync.apply(
        "phone-0001", [QueuedOp("op-2", "notes.edit", {"id": "n1", "expected_version": 1, "fields": {"text": "edited on the phone, offline"}})]
    )[0]
    assert (stale.status, stale.code, stale.current_version) == (
        "conflict",
        "stale_or_missing",
        2,
    )  # the device learns the current version and resolves it with a new operation
    assert rig.store.get("n1").record.fields["text"] == "edited on the Mac"
    resolved = rig.sync.apply("phone-0001", [QueuedOp("op-3", "notes.edit", {"id": "n1", "expected_version": 2, "fields": {"text": "merged"}})])[0]
    assert resolved.status == "applied" and rig.store.get("n1").record.fields["text"] == "merged"


def test_a_revoked_or_unknown_device_has_its_whole_queue_rejected(rig):
    ops = [QueuedOp("op-1", "notes.create", note("n1"))]
    assert [r.status for r in rig.sync.apply("stranger-0001", ops)] == ["rejected"]
    rig.registry.revoke("phone-0001")
    assert [(r.status, r.code) for r in rig.sync.apply("phone-0001", ops)] == [("rejected", "device_not_allowed")] and rig.store.in_domain("notes") == []


def test_a_device_cannot_queue_what_needs_approval_or_touch_a_restricted_domain(rig):
    queue = OfflineQueue()
    for name in ("calendar.send_invitation", "notes.erase", "finance.create", "shop.buy"):
        with pytest.raises(ValueError):
            queue.add("op-x", name, {})
    forged = rig.sync.apply("phone-0001", [QueuedOp("op-1", "notes.erase", {"id": "n1"}), QueuedOp("op-2", "finance.create", {"id": "f1"})])
    assert [(r.status, r.code) for r in forged] == [("rejected", "operation_not_allowed")] * 2  # also refused when a hostile device skips the queue class
    with pytest.raises(ValueError):
        queue.add("dup", "notes.create", note("n1"))
        queue.add("dup", "notes.create", note("n2"))


def test_an_oversized_queue_is_refused_whole(rig):
    ops = [QueuedOp(f"op-{i}", "notes.create", note(f"n{i}")) for i in range(MAX_OPS + 1)]
    assert {r.status for r in rig.sync.apply("phone-0001", ops)} == {"rejected"} and rig.store.in_domain("notes") == []


def test_a_device_cache_holds_only_own_record_domains_and_expires():
    now = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    policy = cache_policy(frozenset({"notes", "finance", "health", "calendar"}), now)
    assert policy.domains == frozenset({"notes", "calendar"}) and policy.expires_at == now + timedelta(days=7) and policy.wipe_on_revocation is True
