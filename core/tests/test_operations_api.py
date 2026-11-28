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
    assert newcomer._json("GET", "/v1/index/status") is not None  # an active paired phone gets 200 on the revocation probe
    assert owner.revoke_device("new-phone-0001") is True
    with pytest.raises(atlas_client.ClientError) as revoked:
        newcomer.sync([{"op_id": "op-0000002", "name": "notes.create", "payload": {**NOTE, "id": "n2"}}])
    assert revoked.value.code == "forbidden" and owner.devices()[0]["revoked_at"] is not None
    with pytest.raises(atlas_client.ClientError) as read_after:
        newcomer.records("notes")  # a revoked device's READ is refused too, not only its writes (what the phone does on its next contact)
    assert read_after.value.code == "forbidden"
    with pytest.raises(atlas_client.ClientError) as probe_after:
        newcomer._json(
            "GET", "/v1/index/status"
        )  # the empty signed request the phone uses to confirm a revocation (a 1.1 route: /v1/version is verified as 1.0)
    assert probe_after.value.code == "forbidden"
    assert [d["device_id"] for d in owner.devices()] == ["new-phone-0001"] and owner._json("GET", "/v1/index/status") is not None  # the owner is unaffected
    with pytest.raises(atlas_client.ClientError) as last:
        owner.revoke_device("client-mac-0001")
    assert last.value.code in ("forbidden", "invalid_request")  # the last owner client cannot be revoked


def test_overlapping_calendar_events_need_attention_and_touching_ones_do_not(world):
    owner = world.client()
    assert owner.attention() == []  # nothing to say: nothing is invented
    for rid, title, start, end in (
        ("e1", "Dentist", "2026-10-20T09:00:00+00:00", "2026-10-20T10:00:00+00:00"),
        ("e2", "Team call", "2026-10-20T09:30:00+00:00", "2026-10-20T10:30:00+00:00"),
        ("e3", "Lunch", "2026-10-20T10:30:00+00:00", "2026-10-20T11:30:00+00:00"),
    ):
        owner.act("calendar.create", {"id": rid, "date": start, "title": title, "fields": {"starts": start, "ends": end}})
    items = owner.attention()
    assert [(i["kind"], i["record_id"], i["priority"]) for i in items] == [("calendar_conflict", "e2", "normal")]  # e3 only touches e2's end
    assert items[0]["title"] == "“Dentist” overlaps “Team call”" and items[0]["key"] == "conflict:e1:e2"
    with pytest.raises(atlas_client.ClientError) as e:
        world.device().attention()
    assert e.value.code == "forbidden"


def test_the_owner_lists_their_own_records_newest_first_with_the_version_an_edit_must_name(world):
    owner = world.client()
    assert owner.records("notes") == []
    owner.act("notes.create", {**NOTE, "id": "n1", "date": "2026-10-18T00:00:00+00:00"})
    owner.act("notes.create", {**NOTE, "id": "n2", "date": "2026-10-19T00:00:00+00:00", "title": "Newer"})
    owner.act("notes.edit", {"id": "n1", "expected_version": 1, "fields": {"text": "Edited."}})
    rows = owner.records("notes")
    assert [(r["id"], r["version"]) for r in rows] == [("n2", 1), ("n1", 2)] and rows[1]["fields"]["text"] == "Edited."
    owner.act("notes.archive", {"id": "n2", "expected_version": 1})
    assert [r["id"] for r in owner.records("notes")] == ["n1"]  # an archived record is not listed (undo brings it back)
    for who in (owner, world.device()):  # Finance and Health are not in this store, for anyone
        with pytest.raises(atlas_client.ClientError) as e:
            who.records("finance")
        assert e.value.code == "not_found"
    assert [r["id"] for r in world.device().records("notes")] == ["n1"]  # a device the owner paired reads the owner's own records
    owner.revoke_device("phone-device-0001")
    with pytest.raises(atlas_client.ClientError) as revoked:
        world.device().records("notes")
    assert revoked.value.code == "forbidden"  # and once revoked it reads nothing


def test_a_trip_is_created_listed_and_undone_like_any_own_record(world):
    owner = world.client()
    out = owner.act(
        "travel.create", {"id": "trip-1", "date": "2026-12-01", "title": "Lisbon", "fields": {"starts": "2026-12-01T09:00:00Z", "booking": "ABC123"}}
    )
    assert out["status"] == "done"
    assert [r["title"] for r in owner.records("travel")] == ["Lisbon"]
    owner.undo(out["action_id"])
    assert owner.records("travel") == []


def _release_folder(folder, version, signer, tag=b"ok"):
    import hashlib
    import io
    import json
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("Atlas.app/Contents/MacOS/Atlas", tag)
    artefact = buffer.getvalue()
    manifest = json.dumps({"version": version, "sha256": hashlib.sha256(artefact).hexdigest(), "size": len(artefact)}).encode()
    folder.mkdir()
    (folder / "manifest.json").write_bytes(manifest)
    (folder / "manifest.sig").write_bytes(signer.sign(manifest))
    (folder / "artefact.zip").write_bytes(artefact)
    return str(folder)


def test_the_owner_installs_a_signed_update_from_a_folder_and_can_go_back_and_a_bad_one_changes_nothing(tmp_path):
    from atlas_core.updater import Installer, UpdateOperations

    signer, stranger = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    root = tmp_path / "install"
    ops = UpdateOperations(Installer(root), signer.public_key())
    (tmp_path / "a").mkdir()
    world = OpsWorld(tmp_path / "a", updates=ops)
    world.build().start()
    try:
        owner = world.client()
        assert owner.update_status() == {"installed": None, "can_roll_back": False}
        first = owner.install_update(_release_folder(tmp_path / "r1", "1.0.0", signer))
        assert first == {"installed": "1.0.0", "restart_needed": True}
        second = owner.install_update(_release_folder(tmp_path / "r2", "1.1.0", signer, b"new"))
        assert second["installed"] == "1.1.0" and owner.update_status() == {"installed": "1.1.0", "can_roll_back": True}
        forged = owner.install_update(_release_folder(tmp_path / "r3", "1.2.0", stranger))
        assert forged == {"installed": None, "restart_needed": False, "refused": "bad_signature"} and owner.update_status()["installed"] == "1.1.0"
        assert owner.install_update(str(tmp_path / "missing"))["refused"] == "bad_release_folder"
        assert owner.install_update(_release_folder(tmp_path / "r4", "1.0.5", signer))["refused"] == "not_newer"  # never backwards by accident
        assert owner.rollback_update() == {"installed": "1.0.0", "restart_needed": True}
        with pytest.raises(atlas_client.ClientError) as e:
            world.device().update_status()  # owner client only
        assert e.value.code == "forbidden"
    finally:
        world.close()


def test_a_core_that_does_not_manage_its_own_install_has_no_update_routes(world):
    with pytest.raises(atlas_client.ClientError) as e:
        world.client().update_status()
    assert e.value.code == "not_found"


def test_the_review_reports_overlapping_calendar_events_from_the_owners_own_calendar(world):
    owner = world.client()
    assert owner.review()["sections"][0] == {"area": "calendar", "state": "ready", "summary": "No events overlap."}
    for rid, title, start, end in (
        ("e1", "Dentist", "2026-12-01T09:00:00+00:00", "2026-12-01T10:00:00+00:00"),
        ("e2", "Team call", "2026-12-01T09:30:00+00:00", "2026-12-01T10:30:00+00:00"),
    ):
        owner.act("calendar.create", {"id": rid, "date": start, "title": title, "fields": {"starts": start, "ends": end}})
    calendar = owner.review()["sections"][0]
    assert calendar["state"] == "ready" and calendar["summary"].startswith("1 event pair overlaps: ") and "Dentist" in calendar["summary"]
    with pytest.raises(atlas_client.ClientError) as e:
        world.device().review()  # owner client only
    assert e.value.code == "forbidden"


def test_approval_state_that_does_not_replay_cleanly_means_the_core_serves_no_actions(tmp_path):
    """ATLAS-ACT-019: a corrupt line in the approval journal (not a torn tail) makes the approval state untrusted, so the Core serves no actions at
    all rather than guess which approvals were used."""
    world = OpsWorld(tmp_path)
    (tmp_path / "core").mkdir(parents=True, exist_ok=True)
    (tmp_path / "core" / "actions-approvals.jsonl").write_text("not a record\n{}\n")
    core = world.build()
    core.start()
    try:
        assert core.operations is None
        with pytest.raises(atlas_client.ClientError):
            world.client().act("notes.create", NOTE)
    finally:
        world.close()
