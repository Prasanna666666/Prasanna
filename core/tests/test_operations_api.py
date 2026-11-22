"""Stages 5 and 6, wired: the owner's actions, approvals, undo and a device's sync are reachable only through the signed API 1.1, on the owner-only socket, and keep every rule the gateway enforces."""

from __future__ import annotations

import pytest
from conftest import KEY
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_app import World
from test_client import atlas_client

from atlas_core.app import Core, CoreConfig

pytestmark = pytest.mark.criterion(5)


class OpsWorld(World):
    def __init__(self, tmp, **extra):
        super().__init__(tmp)
        self.extra, self.sent, self.erased = extra, [], []
        self.clients.register("client-mac-0001", self.key.public_key(), owner=True)
        self.device_key = Ed25519PrivateKey.generate()
        self.clients.register("phone-device-0001", self.device_key.public_key())

    def build(self) -> Core:
        extra = {"edits_key": KEY + "e", "outbox": lambda p: (self.sent.append(p), {"sent": True})[1], "erase": self.erased.append, **self.extra}
        core = Core(
            CoreConfig(
                data_dir=self.tmp / "core", socket_path=self.sock, task_key=KEY + "t", designation_key=KEY + "d", documents_key=KEY + "o", mail_key=KEY + "m", anchor=self.anchor,
                os_permissions=self.os, clients=self.clients, manifest=self.manifest, model_record_key=b"k" * 32, runtime=self.runtime, documents=("documents", self.docs),
                open_bootstrap=True, clock=self.clock, **extra,
            )
        )  # fmt: skip
        self.cores.append(core)
        return core

    def device(self):
        return atlas_client.AtlasClient(str(self.sock), self.device_key, "phone-device-0001", clock=self.clock)


@pytest.fixture
def world(tmp_path):
    w = OpsWorld(tmp_path)
    core = w.build()
    core.start()
    yield w
    w.close()


NOTE = {"id": "n1", "date": "2026-10-18T00:00:00+00:00", "title": "Passport", "fields": {"text": "Renew it."}}


def test_the_owner_creates_edits_and_undoes_a_note_without_a_single_prompt(world):
    client = world.client()
    made = client.act("notes.create", NOTE)
    assert made["status"] == "done" and made["category"] is None and made["result"]["id"] == "n1"
    edited = client.act("notes.edit", {"id": "n1", "expected_version": 1, "fields": {"text": "Renew it before March."}})
    assert edited["status"] == "done"
    assert client.undo(edited["action_id"])["status"] == "done" and world.cores[0].edits.get("n1").record.fields["text"] == "Renew it."
    assert client.undo(edited["action_id"])["code"] == "already_undone"


def test_an_invitation_needs_the_owners_approval_of_exactly_that_payload_and_is_sent_once(world):
    client = world.client()
    payload = {"to": "alex@example.invalid", "event": "e1"}
    first = client.act("calendar.send_invitation", payload)
    assert first["status"] == "needs_approval" and first["category"] == 1 and first["exact_payload"] == payload and world.sent == []
    assert client.approve(first["approval_id"]) is True
    changed = client.act("calendar.send_invitation", {**payload, "to": "other@example.invalid"}, approval_id=first["approval_id"])
    assert changed["status"] == "needs_approval" and world.sent == []  # a material change needs its own approval
    sent = client.act("calendar.send_invitation", payload, approval_id=first["approval_id"])
    assert sent["status"] == "done" and world.sent == [payload]
    assert (
        client.act("calendar.send_invitation", payload, approval_id=first["approval_id"])["status"] == "needs_approval" and len(world.sent) == 1
    )  # single-use


def test_only_the_owner_can_propose_approve_or_undo_and_a_device_cannot(world):
    device = world.device()
    for call in (lambda: device.act("notes.create", NOTE), lambda: device.approve("0" * 16), lambda: device.undo("0" * 16)):
        with pytest.raises(atlas_client.ClientError) as e:
            call()
        assert e.value.code == "forbidden"
    assert world.cores[0].edits.in_domain("notes") == []


def test_an_unknown_action_and_a_malformed_request_are_refused_with_a_code(world):
    client = world.client()
    assert client.act("shop.buy", {"amount": "9.99"})["code"] == "unknown_action"  # nothing registers a spending action in this Core
    with pytest.raises(atlas_client.ClientError) as e:
        client._json("POST", "/v1/actions", {"action": "Not A Name", "payload": {}, "idempotency_key": "k"})
    assert e.value.code == "invalid_request"


def test_a_device_syncs_its_offline_queue_once_and_conflicts_are_reported(world):
    device, owner = world.device(), world.client()
    ops = [
        {"op_id": "op-0000001", "name": "notes.create", "payload": NOTE},
        {"op_id": "op-0000002", "name": "notes.edit", "payload": {"id": "n1", "expected_version": 1, "fields": {"text": "from phone"}}},
    ]
    assert [r["status"] for r in device.sync(ops)] == ["applied", "applied"]
    assert [r["status"] for r in device.sync(ops)] == ["duplicate", "duplicate"]
    assert owner.act("notes.edit", {"id": "n1", "expected_version": 2, "fields": {"text": "from the Mac"}})["status"] == "done"
    stale = device.sync([{"op_id": "op-0000003", "name": "notes.edit", "payload": {"id": "n1", "expected_version": 2, "fields": {"text": "stale"}}}])[0]
    assert (stale["status"], stale["current_version"]) == ("conflict", 3) and world.cores[0].edits.get("n1").record.fields["text"] == "from the Mac"
    forbidden = device.sync([{"op_id": "op-0000004", "name": "calendar.send_invitation", "payload": {"to": "x@example.invalid"}}])[0]
    assert forbidden["status"] == "rejected" and world.sent == []  # a device cannot cause a send


def test_a_core_without_an_edits_key_has_no_actions_and_no_sync_at_all(tmp_path):
    bare = OpsWorld(tmp_path, edits_key=None)
    core = bare.build()
    core.start()
    try:
        with pytest.raises(atlas_client.ClientError) as e:
            bare.client().act("notes.create", NOTE)
        assert e.value.code == "not_found" and core.operations is None
    finally:
        bare.close()


def test_the_erase_action_exists_only_with_a_platform_eraser_and_always_needs_approval(world, tmp_path):
    client = world.client()
    client.act("notes.create", NOTE)
    pending = client.act("notes.erase", {"id": "n1"})
    assert pending["status"] == "needs_approval" and pending["category"] == 3 and world.erased == []
    client.approve(pending["approval_id"])
    assert client.act("notes.erase", {"id": "n1"}, approval_id=pending["approval_id"])["status"] == "done" and world.erased == ["n1"]
    (tmp_path / "other").mkdir()
    other = OpsWorld(tmp_path / "other", erase=None)
    core = other.build()
    core.start()
    try:
        assert other.client().act("notes.erase", {"id": "n1"})["code"] == "unknown_action"  # no eraser configured: the action does not exist
    finally:
        other.close()


def test_a_damaged_audit_file_means_the_core_serves_no_actions_at_all(tmp_path):
    first = OpsWorld(tmp_path)
    core = first.build()
    core.start()
    first.client().act("notes.create", NOTE)
    first.close()
    audit = tmp_path / "core" / "actions-audit.jsonl"
    audit.write_text(audit.read_text().replace('"done"', '"refused"'))
    (tmp_path / "again").mkdir()
    second = OpsWorld(tmp_path / "again")
    (tmp_path / "again" / "core" / "actions-audit.jsonl").write_text(audit.read_text())
    core2 = second.build()
    core2.start()
    try:
        assert core2.operations is None
        with pytest.raises(atlas_client.ClientError) as e:
            second.client().act("notes.create", NOTE)
        assert e.value.code == "not_found"
    finally:
        second.close()


def test_a_device_pairs_over_the_socket_checks_the_core_syncs_and_is_revoked_for_good(world):
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from atlas_core.devices import verify_core

    owner = world.client()
    offer = owner.open_pairing_offer()
    new_key = Ed25519PrivateKey.generate()
    newcomer = atlas_client.AtlasClient(str(world.sock), new_key, "new-phone-0001", clock=world.clock)
    public = base64.b64encode(new_key.public_key().public_bytes_raw()).decode()
    with pytest.raises(atlas_client.ClientError) as wrong:
        newcomer.pair_device("not-the-code-at-all", "new-phone-0001", "Phone", public, "nonce-abcdefgh")
    assert wrong.value.code == "forbidden"  # a wrong code and an expired or spent one answer the same way
    paired = newcomer.pair_device(offer["code"], "new-phone-0001", "Phone", public, "nonce-abcdefgh")
    core_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(paired["core_public_key"]))
    assert verify_core(
        offer["core_fingerprint"], core_key, base64.b64decode(paired["proof"]), new_key.public_key(), "nonce-abcdefgh"
    )  # the device can check it paired with the right Core
    with pytest.raises(atlas_client.ClientError):
        newcomer.pair_device(offer["code"], "second-phone-001", "Other", public, "nonce-abcdefgh")  # single-use
    assert newcomer.sync([{"op_id": "op-0000001", "name": "notes.create", "payload": NOTE}])[0]["status"] == "applied"
    with pytest.raises(atlas_client.ClientError) as member:
        newcomer.open_pairing_offer()  # a paired device is a member, never an owner
    assert member.value.code == "forbidden"
    assert [(d["device_id"], d["label"], d["revoked_at"]) for d in owner.devices()] == [("new-phone-0001", "Phone", None)]
    assert owner.revoke_device("new-phone-0001") is True
    with pytest.raises(atlas_client.ClientError) as revoked:
        newcomer.sync([{"op_id": "op-0000002", "name": "notes.create", "payload": {**NOTE, "id": "n2"}}])
    assert revoked.value.code == "forbidden" and owner.devices()[0]["revoked_at"] is not None
    with pytest.raises(atlas_client.ClientError) as last:
        owner.revoke_device("client-mac-0001")
    assert last.value.code in ("forbidden", "invalid_request")  # the last owner client cannot be revoked
