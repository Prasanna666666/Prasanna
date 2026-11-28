"""Stage 6: the Action Gateway. Approval only for PRD 4.4's four categories, single-use and bound to the exact payload, content is never the owner, idempotent, undoable, audited, revocable."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from conftest import KEY

from atlas_core.actions import CATEGORY, ActionGateway, ActionSpec, run_workflow
from atlas_core.record_actions import register_record_actions
from atlas_core.recordstore import RecordStore

pytestmark = pytest.mark.criterion(5)


class Outbox:
    def __init__(self):
        self.sent = []

    def __call__(self, payload):
        self.sent.append(payload)
        return {"sent_to": payload["to"]}


@pytest.fixture
def rig(tmp_path):
    store = RecordStore(tmp_path / "edits.db", KEY + "e", frozenset({"calendar", "contacts", "notes"}))
    gateway, outbox, purged = ActionGateway(), Outbox(), []
    register_record_actions(gateway, store, outbox, purged.append)
    yield gateway, store, outbox, purged
    store.close()


def event(rid="e1", **extra):
    return {"id": rid, "date": "2026-10-20T09:00:00+00:00", "title": "Dentist", "fields": {"starts": "2026-10-20T09:00:00+00:00", **extra}}


def own(gateway, name, payload, key):
    return gateway.propose(name, payload, origin="owner_request", idempotency_key=key)


def test_the_action_matrix_only_the_four_categories_ever_need_approval(rig):
    gateway = rig[0]
    gateway.register(ActionSpec("shop.buy", frozenset({"spend"}), lambda p: {"ok": True}, connector="shop"))
    gateway.register(ActionSpec("door.unlock", frozenset({"physical_security"}), lambda p: {"ok": True}))
    gateway.register(ActionSpec("web.lookup", frozenset({"read"}), lambda p: {"ok": True}))
    categories = {s.name: s.category for s in gateway.specs()}
    assert set(CATEGORY.values()) == {1, 2, 3, 4}
    assert categories["calendar.send_invitation"] == 1 and categories["shop.buy"] == 2 and categories["notes.erase"] == 3 and categories["door.unlock"] == 4
    for name in (
        "calendar.create",
        "calendar.edit",
        "calendar.archive",
        "contacts.create",
        "contacts.edit",
        "notes.create",
        "notes.edit",
        "notes.archive",
        "web.lookup",
    ):
        assert categories[name] is None, name  # everything else never prompts
    with pytest.raises(ValueError):
        ActionSpec("bad.reversible", frozenset({"local_reversible"}), lambda p: {})  # claims to be reversible but cannot undo
    with pytest.raises(ValueError):
        ActionSpec("bad.effect", frozenset({"anything_else"}), lambda p: {})  # no open-ended category


def test_own_calendar_and_notes_changes_never_prompt_and_every_one_can_be_undone(rig):
    gateway, store, _, _ = rig
    created = own(gateway, "calendar.create", event(), "k1")
    moved = own(gateway, "calendar.edit", {"id": "e1", "expected_version": 1, "date": "2026-10-21T09:00:00+00:00"}, "k2")
    note = own(gateway, "notes.create", {"id": "n1", "date": "2026-10-18T00:00:00+00:00", "title": "Passport", "fields": {"text": "Renew it."}}, "k3")
    assert [o.status for o in (created, moved, note)] == ["done"] * 3 and gateway.prompts == 0
    assert store.get("e1").record.date.startswith("2026-10-21") and store.get("e1").version == 2
    assert gateway.undo(moved.action_id).status == "done" and store.get("e1").record.date.startswith("2026-10-20")
    assert gateway.undo(moved.action_id).code == "already_undone"
    assert gateway.undo(created.action_id).status == "done" and store.in_domain("calendar") == []


def test_sending_an_invitation_needs_approval_bound_to_the_exact_payload_and_is_single_use(rig):
    gateway, _, outbox, _ = rig
    payload = {"to": "alex@example.invalid", "event": "e1", "when": "2026-10-20T09:00:00+00:00"}
    first = own(gateway, "calendar.send_invitation", payload, "s1")
    assert first.status == "needs_approval" and first.category == 1 and first.exact_payload == payload and outbox.sent == [] and gateway.prompts == 1
    assert gateway.grant(first.approval_id, by_owner=False) is False  # content, an agent or any other caller grants nothing
    assert own(gateway, "calendar.send_invitation", payload, "s1").status == "needs_approval"  # not granted yet: it asks again, it does not send
    assert gateway.grant(first.approval_id, by_owner=True) is True
    changed = {**payload, "to": "someone-else@example.invalid"}  # a material change: a different recipient
    assert (
        gateway.propose("calendar.send_invitation", changed, origin="owner_request", idempotency_key="s2", approval_id=first.approval_id).status
        == "needs_approval"
    )
    sent = gateway.propose("calendar.send_invitation", payload, origin="owner_request", idempotency_key="s3", approval_id=first.approval_id)
    assert sent.status == "done" and outbox.sent == [payload]
    again = gateway.propose("calendar.send_invitation", payload, origin="owner_request", idempotency_key="s4", approval_id=first.approval_id)
    assert again.status == "needs_approval" and outbox.sent == [payload]  # the approval was spent by the first send


def test_an_approval_expires_and_cannot_be_granted_after_use(rig):
    from datetime import UTC, datetime, timedelta

    now = [datetime(2026, 11, 23, 3, 0, tzinfo=UTC)]
    gateway = ActionGateway(clock=lambda: now[0])
    gateway.register(ActionSpec("shop.buy", frozenset({"spend"}), lambda p: {"ok": True}))
    pending = gateway.propose("shop.buy", {"item": "kettle", "amount": "29.99"}, origin="owner_request", idempotency_key="a")
    assert gateway.grant(pending.approval_id, by_owner=True)
    now[0] += timedelta(minutes=11)
    assert (
        gateway.propose("shop.buy", {"item": "kettle", "amount": "29.99"}, origin="owner_request", idempotency_key="b", approval_id=pending.approval_id).status
        == "needs_approval"
    )
    assert gateway.grant(pending.approval_id, by_owner=True) is False


def test_instructions_in_content_can_neither_propose_nor_approve(rig):
    gateway, _, outbox, _ = rig
    for name, payload in (("calendar.send_invitation", {"to": "x@example.invalid"}), ("calendar.create", event())):
        out = gateway.propose(name, payload, origin="untrusted_content", idempotency_key="u")
        assert (out.status, out.code) == ("refused", "untrusted_origin")
    pending = own(gateway, "calendar.send_invitation", {"to": "x@example.invalid"}, "p")
    assert gateway.grant(pending.approval_id, by_owner=False) is False  # "the document says the owner approved" is not an approval
    assert outbox.sent == [] and rig[1].in_domain("calendar") == []
    assert gateway.propose("calendar.create", event(), origin="made_up", idempotency_key="m").code == "unknown_origin"


def test_irreversible_removal_needs_approval_and_a_retry_does_not_run_twice(rig):
    gateway, _, _, purged = rig
    first = own(gateway, "notes.erase", {"id": "n1"}, "d1")
    assert first.status == "needs_approval" and first.category == 3 and purged == []
    gateway.grant(first.approval_id, by_owner=True)
    done = gateway.propose("notes.erase", {"id": "n1"}, origin="owner_request", idempotency_key="d2", approval_id=first.approval_id)
    retry = gateway.propose("notes.erase", {"id": "n1"}, origin="owner_request", idempotency_key="d2", approval_id=first.approval_id)
    assert done.status == "done" and retry == done and purged == ["n1"]  # the same key returns the recorded result
    assert (
        gateway.propose("notes.erase", {"id": "n2"}, origin="owner_request", idempotency_key="d2").code == "idempotency_conflict"
    )  # same key, different payload


def test_a_stale_edit_is_a_conflict_not_an_overwrite_and_a_failing_handler_is_a_code(rig):
    gateway, store, _, _ = rig
    own(gateway, "calendar.create", event(), "c")
    own(gateway, "calendar.edit", {"id": "e1", "expected_version": 1, "title": "Dentist (moved)"}, "e1")
    stale = own(gateway, "calendar.edit", {"id": "e1", "expected_version": 1, "title": "Overwrite"}, "e2")
    assert (stale.status, stale.code) == ("failed", "handler_failed") and store.get("e1").record.title == "Dentist (moved)"
    assert "conflict" not in repr(stale)  # the outcome carries a code, never the error text


def test_a_revoked_connector_refuses_every_one_of_its_actions(rig):
    gateway = rig[0]
    calls = []
    gateway.register(
        ActionSpec("home.heating", frozenset({"local_reversible"}), lambda p: calls.append(p) or {"ok": True}, lambda p, r: None, connector="home")
    )
    assert own(gateway, "home.heating", {"set": 19}, "h1").status == "done"
    gateway.revoke_connector("home")
    assert own(gateway, "home.heating", {"set": 21}, "h2").code == "connector_revoked" and calls == [{"set": 19}]


def test_the_audit_is_chained_content_free_and_tampering_is_detected(rig):
    gateway = rig[0]
    own(gateway, "notes.create", {"id": "n1", "date": "2026-10-18T00:00:00+00:00", "title": "Sentinel title 4929", "fields": {"text": "Sentinel body"}}, "a1")
    own(gateway, "calendar.send_invitation", {"to": "x@example.invalid"}, "a2")
    assert gateway.verify_audit() and [e.outcome for e in gateway.audit] == ["done", "needs_approval"]
    assert "Sentinel" not in repr(gateway.audit) and "example.invalid" not in repr(gateway.audit)
    gateway.audit[0] = type(gateway.audit[0])(**{**gateway.audit[0].__dict__, "outcome": "refused"})
    assert gateway.verify_audit() is False


def test_a_workflow_takes_back_what_it_did_when_a_step_fails_or_it_is_cancelled(rig):
    gateway, store, _, _ = rig
    steps = [
        ("calendar.create", event()),
        ("notes.create", {"id": "n1", "date": "2026-10-18T00:00:00+00:00", "title": "Prep", "fields": {"text": "Bring ID."}}),
        ("calendar.edit", {"id": "zzz", "expected_version": 1}),
    ]
    report = run_workflow(gateway, steps, key="w1")
    assert (
        report.status == "failed_rolled_back"
        and report.completed == ["calendar.create", "notes.create"]
        and report.compensated == ["notes.create", "calendar.create"]
    )
    assert store.in_domain("calendar") == [] and store.in_domain("notes") == []
    stop = {"now": False}
    steps2 = [("calendar.create", event("e2")), ("notes.create", {"id": "n2", "date": "2026-10-18T00:00:00+00:00", "title": "Prep", "fields": {"text": "x"}})]
    report2 = run_workflow(gateway, steps2, key="w2", cancelled=lambda: (stop.__setitem__("now", len(store.in_domain("calendar")) > 0), stop["now"])[1])
    assert (
        report2.status == "cancelled"
        and report2.completed == ["calendar.create"]
        and report2.compensated == ["calendar.create"]
        and store.in_domain("calendar") == []
    )


def test_a_workflow_stops_at_a_step_that_needs_approval_and_reports_a_step_that_cannot_be_taken_back(rig):
    gateway, _, outbox, _ = rig
    report = run_workflow(
        gateway,
        [
            ("calendar.create", event()),
            ("calendar.send_invitation", {"to": "x@example.invalid"}),
            ("notes.create", {"id": "n1", "date": "2026-10-18T00:00:00+00:00", "title": "t", "fields": {"text": "x"}}),
        ],
        key="w3",
    )
    assert report.status == "needs_approval" and report.completed == ["calendar.create"] and outbox.sent == []  # nothing after the approval step ran
    gateway.register(ActionSpec("odd.step", frozenset({"local_reversible"}), lambda p: {}, lambda p, r: (_ for _ in ()).throw(RuntimeError("cannot undo"))))
    gateway.register(ActionSpec("fail.step", frozenset({"read"}), lambda p: (_ for _ in ()).throw(RuntimeError("boom"))))
    stuck = run_workflow(gateway, [("odd.step", {}), ("fail.step", {})], key="w4")
    assert stuck.status == "failed_partial" and stuck.stuck == ["odd.step"]  # never reported as all is well


def test_the_audit_is_written_to_disk_before_the_outcome_continues_after_a_restart_and_a_damaged_file_stops_the_actions(tmp_path):
    from atlas_core.actions import AuditFile

    file = AuditFile(tmp_path / "audit.jsonl")
    first = ActionGateway(audit_file=file, history=file.load())
    first.register(ActionSpec("web.lookup", frozenset({"read"}), lambda p: {"ok": True}))
    first.register(ActionSpec("shop.buy", frozenset({"spend"}), lambda p: {"ok": True}))
    first.propose("web.lookup", {"q": "SENTINEL-QUERY"}, origin="owner_request", idempotency_key="a")
    first.propose("shop.buy", {"item": "x"}, origin="owner_request", idempotency_key="b")
    assert oct((tmp_path / "audit.jsonl").stat().st_mode & 0o777) == "0o600" and "SENTINEL-QUERY" not in (tmp_path / "audit.jsonl").read_text()
    again = ActionGateway(audit_file=file, history=file.load())  # a restart
    again.register(ActionSpec("web.lookup", frozenset({"read"}), lambda p: {"ok": True}))
    again.propose("web.lookup", {"q": "again"}, origin="owner_request", idempotency_key="c")
    assert [e.seq for e in again.audit] == [1, 2, 3] and again.verify_audit() and file.load() is not None and len(file.load()) == 3
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    for damaged in (lines[1:], [lines[1], lines[0], lines[2]], [*lines[:-1], lines[-1].replace('"done"', '"refused"')], ["{not json}"]):
        (tmp_path / "audit.jsonl").write_text("\n".join(damaged) + "\n")
        assert file.load() is None  # a missing, reordered, edited or unreadable line: the history cannot be vouched for


def test_an_ambiguous_external_failure_is_never_run_again_with_the_same_key_even_after_a_restart(tmp_path):
    """ATLAS-ACT-026 / ATLAS-ACT-019: a connector action that raises after the provider may have committed is recorded as outcome_unknown; a retry (and a retry after restart) does not repeat the side effect."""
    from atlas_core.actions import ActionNotPerformed, IdempotencyFile

    sent: list[str] = []

    def flaky_send(payload):
        sent.append(payload["to"])  # the remote service commits...
        raise TimeoutError("response lost")  # ...but the reply never arrives

    def build():
        g = ActionGateway(idempotency=IdempotencyFile(tmp_path / "idem.jsonl"))
        g.register(ActionSpec("mail.send", frozenset({"external_send"}), flaky_send, connector="mail"))
        g.register(ActionSpec("mail.draft", frozenset({"read"}), lambda p: (_ for _ in ()).throw(ActionNotPerformed()), connector="mail"))
        return g

    g = build()
    first = g.propose("mail.send", {"to": "a@example.test"}, origin="owner_request", idempotency_key="k1", approval_id=None)
    assert first.status == "needs_approval"
    assert g.grant(first.approval_id, by_owner=True)
    ambiguous = g.propose("mail.send", {"to": "a@example.test"}, origin="owner_request", idempotency_key="k1", approval_id=first.approval_id)
    assert (ambiguous.status, ambiguous.code) == ("failed", "outcome_unknown") and sent == ["a@example.test"]
    again = g.propose("mail.send", {"to": "a@example.test"}, origin="owner_request", idempotency_key="k1")
    assert again.code == "outcome_unknown" and sent == ["a@example.test"]  # not run again
    restarted = build()
    after = restarted.propose("mail.send", {"to": "a@example.test"}, origin="owner_request", idempotency_key="k1")
    assert after.code == "outcome_unknown" and sent == ["a@example.test"]
    assert restarted.propose("mail.send", {"to": "b@example.test"}, origin="owner_request", idempotency_key="k1").code == "idempotency_conflict"
    # a handler that proves it did nothing may be retried under the same key
    assert restarted.propose("mail.draft", {}, origin="owner_request", idempotency_key="d1").code == "handler_failed"
    assert restarted.propose("mail.draft", {}, origin="owner_request", idempotency_key="d1").code == "handler_failed"
    assert "a@example.test" not in (tmp_path / "idem.jsonl").read_text() and oct((tmp_path / "idem.jsonl").stat().st_mode & 0o777) == "0o600"


def test_a_completed_action_replayed_after_a_restart_is_answered_done_and_not_run_again(tmp_path):
    from atlas_core.actions import IdempotencyFile

    runs: list[int] = []

    def build():
        g = ActionGateway(idempotency=IdempotencyFile(tmp_path / "idem.jsonl"))
        g.register(ActionSpec("note.write", frozenset({"local_reversible"}), lambda p: runs.append(1) or {"ok": True}, undo=lambda p, r: None))
        return g

    first = build().propose("note.write", {"t": "x"}, origin="owner_request", idempotency_key="k")
    again = build().propose("note.write", {"t": "x"}, origin="owner_request", idempotency_key="k")
    assert (first.status, again.status, again.action_id) == ("done", "done", first.action_id) and runs == [1]


def test_an_action_done_before_a_restart_can_still_be_undone_after_it_exactly_once(tmp_path):
    """ATLAS-ACT-019, UC-L14: the receipt an undo needs (action name, payload and result) is written to the owner's encrypted edits store before
    the outcome returns. After a restart (a new gateway, the same store) the owner's undo works, and a second undo after another restart is
    refused as already undone. An unknown id, or an id whose action is not registered in this run, is refused, never guessed."""
    store_path = tmp_path / "edits.db"

    def gateway():
        store = RecordStore(store_path, KEY + "e", frozenset({"calendar", "contacts", "notes"}))
        g = ActionGateway(receipts=store)
        register_record_actions(g, store, Outbox(), lambda _rid: None)
        return g, store

    g, store = gateway()
    created = own(g, "calendar.create", event(), "c1")
    assert created.status == "done" and store.get("e1").record.title == "Dentist"
    store.close()
    g, store = gateway()  # a restart
    undone = g.undo(created.action_id)
    assert (undone.status, undone.code) == ("done", "undone") and store.get("e1", include_deleted=True).deleted
    assert g.undo("0" * 16).code == "unknown_action_id"
    store.close()
    g, store = gateway()  # another restart
    assert g.undo(created.action_id).code == "already_undone"
    bare = ActionGateway(receipts=store)  # nothing registered in this run: the receipt is not enough to run anything
    assert bare.undo(created.action_id).code == "unknown_action_id"
    store.close()


def test_an_approval_granted_before_a_restart_is_honoured_once_after_it_and_never_twice(tmp_path):
    """ATLAS-ACT-019: approvals survive a restart without their payload (id, binding hash, category, expiry, granted, used). An approval granted
    before a restart runs its exact action once after it; its `used` mark is on disk before the action runs, so another restart cannot use it
    again; and an approval that expired meanwhile is refused."""
    from atlas_core.actions import ApprovalFile

    store_path, file = tmp_path / "edits.db", ApprovalFile(tmp_path / "approvals.jsonl")
    clock = {"now": datetime(2026, 11, 28, 9, 0, tzinfo=UTC)}

    def gateway():
        store = RecordStore(store_path, KEY + "e", frozenset({"calendar", "contacts", "notes"}))
        outbox = Outbox()
        g = ActionGateway(lambda: clock["now"], approvals=file)
        register_record_actions(g, store, outbox, lambda _rid: None)
        return g, store, outbox

    g, store, _ = gateway()
    pending = own(g, "calendar.send_invitation", {"to": "x@example.invalid"}, "p1")
    assert pending.status == "needs_approval" and g.grant(pending.approval_id, by_owner=True)
    assert "x@example.invalid" not in (tmp_path / "approvals.jsonl").read_text()  # never the payload
    store.close()
    g, store, outbox = gateway()  # a restart
    done = g.propose("calendar.send_invitation", {"to": "x@example.invalid"}, origin="owner_request", idempotency_key="s1", approval_id=pending.approval_id)
    assert done.status == "done" and len(outbox.sent) == 1
    store.close()
    g, store, outbox = gateway()  # another restart: the approval was used
    again = g.propose("calendar.send_invitation", {"to": "x@example.invalid"}, origin="owner_request", idempotency_key="s2", approval_id=pending.approval_id)
    assert again.status == "needs_approval" and outbox.sent == []
    late = own(g, "calendar.send_invitation", {"to": "y@example.invalid"}, "p2")
    g.grant(late.approval_id, by_owner=True)
    store.close()
    clock["now"] += timedelta(hours=1)
    g, store, outbox = gateway()  # restarted after it expired
    expired = g.propose("calendar.send_invitation", {"to": "y@example.invalid"}, origin="owner_request", idempotency_key="s3", approval_id=late.approval_id)
    assert expired.status == "needs_approval" and outbox.sent == []
    store.close()


def test_a_torn_approval_record_never_absorbs_the_next_state_and_corruption_elsewhere_fails_closed(tmp_path):
    """ATLAS-ACT-019 (review 6097009203): an interrupted write leaves a partial last line. The next append cuts it off first, so the acknowledged
    `used` state that follows is replayed on the next load and the approval stays consumed. A bad line that is not the torn tail makes the whole
    state untrusted (the Core then serves no actions), never silently skipped."""
    from atlas_core.actions import Approval, ApprovalFile

    path = tmp_path / "approvals.jsonl"
    book = ApprovalFile(path)
    expires = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
    book.append(Approval("a1a1a1a1a1a1a1a1", "b" * 64, 1, expires, granted=True))
    with open(path, "ab") as handle:
        handle.write(b'{"id": "a1a1a1a1a1a1a1a1", "binding": "')  # the write that was interrupted: no newline
    book.append(Approval("a1a1a1a1a1a1a1a1", "b" * 64, 1, expires, granted=True, used=True))
    assert book.load()["a1a1a1a1a1a1a1a1"].used is True  # the acknowledged state survives; nothing was absorbed into the torn tail
    path.write_text(path.read_text() + "not a record\n" + path.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="approval_state_corrupt"):
        ApprovalFile(path).load()


@pytest.mark.parametrize(
    "bad",
    [
        {"granted": "true"},  # a string is not a boolean
        {"category": True},  # a boolean is not a category
        {"category": 9},  # not one of the four
        {"expires_at": "2026-11-28T10:00:00"},  # no timezone
        {"id": "short"},
        {"extra": 1},
    ],
)
def test_approval_replay_takes_no_record_that_is_not_exactly_of_its_form(tmp_path, bad):
    """ATLAS-ACT-019 (review 6097249161): replay coerces nothing. A record with a wrong type, an unknown category, a time without a timezone,
    a malformed id or an extra field makes the state untrusted."""
    from atlas_core.actions import ApprovalFile

    row = {"id": "a1a1a1a1a1a1a1a1", "binding": "b" * 64, "category": 1, "expires_at": "2026-11-28T10:00:00+00:00", "granted": True, "used": False}
    (tmp_path / "approvals.jsonl").write_text(json.dumps({**row, **bad}) + "\n")
    with pytest.raises(ValueError, match="approval_state_corrupt"):
        ApprovalFile(tmp_path / "approvals.jsonl").load()


@pytest.mark.parametrize("change", [{"used": False}, {"granted": False, "used": False}, {"binding": "c" * 64}, {"category": 2}])
def test_approval_replay_refuses_a_record_that_moves_an_approval_backwards_or_changes_what_it_binds(tmp_path, change):
    """A used approval cannot become unused again, a granted one cannot be un-granted, and no later record may change the binding, category or
    expiry: any of these makes the state untrusted (the Core then serves no actions)."""
    from atlas_core.actions import ApprovalFile

    row = {"id": "a1a1a1a1a1a1a1a1", "binding": "b" * 64, "category": 1, "expires_at": "2026-11-28T10:00:00+00:00", "granted": True, "used": True}
    (tmp_path / "approvals.jsonl").write_text(json.dumps(row) + "\n" + json.dumps({**row, **change}) + "\n")
    with pytest.raises(ValueError, match="approval_state_corrupt"):
        ApprovalFile(tmp_path / "approvals.jsonl").load()


class ConnectionProxy:
    """Wraps a store's connection to inject a fault just before one statement runs (the real connection's methods are read-only)."""

    def __init__(self, conn, before):
        self._conn, self._before = conn, before

    def execute(self, sql, *args):
        self._before(sql)
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


_KILLED_UNDO = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from conftest import KEY
from test_actions import Outbox
from atlas_core.actions import ActionGateway
from atlas_core.record_actions import register_record_actions
from atlas_core.recordstore import RecordStore
store = RecordStore(Path(sys.argv[1]), KEY + "e", frozenset({"calendar", "contacts", "notes"}))
from test_actions import ConnectionProxy
store._conn = ConnectionProxy(store._conn, lambda sql: os._exit(9) if sql.startswith("UPDATE receipts SET undone=1") else None)  # killed inside the undo transaction
gateway = ActionGateway(receipts=store)
register_record_actions(gateway, store, Outbox(), lambda _rid: None)
gateway.undo(sys.argv[2])
"""


def test_an_undo_killed_between_its_effect_and_its_receipt_mark_leaves_neither_and_is_done_exactly_once_after_restart(tmp_path):
    """UC-L14 (review 6097009203): the undo's effect and the receipt's undone mark are one transaction. The process is killed (os._exit, no
    handler runs) after the reversal was written and before commit: after the restart the record is unchanged and the receipt still eligible,
    so the owner's undo runs once, and a second undo is refused. Neither a lost undo nor a double undo is possible."""
    import subprocess
    import sys
    from pathlib import Path

    store_path = tmp_path / "edits.db"
    store = RecordStore(store_path, KEY + "e", frozenset({"calendar", "contacts", "notes"}))
    gateway = ActionGateway(receipts=store)
    register_record_actions(gateway, store, Outbox(), lambda _rid: None)
    created = own(gateway, "calendar.create", event(), "c1")
    store.close()
    done = subprocess.run(
        [sys.executable, "-c", _KILLED_UNDO, str(store_path), created.action_id, str(Path(__file__).parent)], check=False, capture_output=True
    )
    assert done.returncode == 9, done.stderr
    store = RecordStore(store_path, KEY + "e", frozenset({"calendar", "contacts", "notes"}))
    try:
        assert not store.get("e1", include_deleted=True).deleted and store.receipt(created.action_id)[3] is False  # nothing of the undo committed
        gateway = ActionGateway(receipts=store)
        register_record_actions(gateway, store, Outbox(), lambda _rid: None)
        assert gateway.undo(created.action_id).code == "undone" and store.get("e1", include_deleted=True).deleted
        assert gateway.undo(created.action_id).code == "already_undone"
    finally:
        store.close()


def test_an_undo_that_fails_inside_its_transaction_changes_nothing_and_can_be_retried(tmp_path, monkeypatch):
    """The same boundary without a kill: a failure inside the undo transaction rolls the reversal back with the receipt's mark, the owner sees
    `undo_failed`, and a retry succeeds once."""
    store = RecordStore(tmp_path / "edits.db", KEY + "e", frozenset({"calendar", "contacts", "notes"}))
    gateway = ActionGateway(receipts=store)
    register_record_actions(gateway, store, Outbox(), lambda _rid: None)
    created = own(gateway, "calendar.create", event(), "c1")
    real = store._conn

    def fail_at_marker(sql):
        if sql.startswith("UPDATE receipts SET undone=1"):
            raise OSError("disk full at the marker")

    store._conn = ConnectionProxy(real, fail_at_marker)
    try:
        assert gateway.undo(created.action_id).code == "undo_failed"
        store._conn = real
        assert not store.get("e1", include_deleted=True).deleted and store.receipt(created.action_id)[3] is False
        assert gateway.undo(created.action_id).code == "undone" and gateway.undo(created.action_id).code == "already_undone"
    finally:
        store.close()
