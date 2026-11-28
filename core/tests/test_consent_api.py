"""API 1.1 consent and index-status routes, served by a whole Core: owner-only, replay-protected, audited, and a withdrawal purges what was derived."""

from __future__ import annotations

import json
import sys
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_app import World, atlas_client

from atlas_core import contracts
from atlas_core.api import Request
from atlas_core.identity import sign_request

pytestmark = pytest.mark.skipif(sys.platform not in ("linux", "darwin"), reason="peer credentials are implemented for Linux and macOS only")
OWNER = "owner-mac-0001"


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    w.owner_key = Ed25519PrivateKey.generate()
    w.clients.register(OWNER, w.owner_key.public_key(), owner=True)
    yield w
    w.close()


def owner(w: World, **kw) -> atlas_client.AtlasClient:
    return atlas_client.AtlasClient(str(w.sock), w.owner_key, OWNER, clock=w.clock, **kw)


def call(core, w, key, client, method, target, body=b"", version="1.1"):
    headers = sign_request(key, client, method, target, body, w.clock(), version=version)
    return core.api.handle(Request(method, target, headers, body))


def test_only_an_enrolled_owner_client_may_read_or_change_consent_and_any_client_may_read_index_counts(world):
    core = world.build()
    core.start()
    plain = world.client()  # enrolled, but not an owner client
    for action in (plain.consent, lambda: plain.enable(["documents"]), lambda: plain.withdraw("grant-0000001")):
        with pytest.raises(atlas_client.ClientError) as e:
            action()
        assert e.value.code == "forbidden"
    assert plain.index_status()["state"] in ("idle", "building") and core.designation.latest_grants(["documents"]) == []
    assert owner(world).consent() == {"grants": [], "sources": [{"source_type": s, "os_access": "unknown"} for s in core.designation.designable()]}


def test_a_1_0_request_cannot_reach_these_routes(world):
    core = world.build()
    for method, target in (("GET", "/v1/consent"), ("POST", "/v1/consent"), ("DELETE", "/v1/consent/grant-0000001"), ("GET", "/v1/index/status")):
        assert call(core, world, world.owner_key, OWNER, method, target, b'{"sources":["documents"]}' if method == "POST" else b"", version="1.0").status == 404
    assert core.designation.latest_grants(["documents"]) == []


def test_get_started_enables_a_source_the_core_indexes_it_and_status_reports_counts_only(world):
    core = world.build()
    core.start()
    world.os.set("documents", "granted")
    state = owner(world).enable(["documents"])
    contracts.validate("ConsentState", state, "1.1")
    assert [g["source_type"] for g in state["grants"]] == ["documents"] and state["grants"][0]["revoked"] is False
    world.wait_indexed(core)
    status = owner(world).index_status()
    contracts.validate("IndexStatus", status, "1.1")
    from atlas_core.documents import iso_utc

    newest = iso_utc(max(p.stat().st_mtime for p in world.docs.rglob("*") if p.is_file()))
    assert status["state"] == "idle" and status["indexed"] == status["total"] > 0 and status["newest_indexed"] == newest  # UC-L26: the newest item's own time
    assert "1250.50" not in json.dumps(status) and "invoice" not in json.dumps(status)
    owner(world).withdraw(state["grants"][0]["grant_id"])
    assert owner(world).index_status()["newest_indexed"] is None  # a withdrawn source contributes nothing, not even a timestamp


def test_a_replayed_request_changes_nothing(world):
    core = world.build()
    core.start()
    world.os.set("documents", "granted")
    body = json.dumps({"sources": ["documents"]}).encode()
    headers = sign_request(world.owner_key, OWNER, "POST", "/v1/consent", body, world.clock(), version="1.1")
    assert core.api.handle(Request("POST", "/v1/consent", headers, body)).status == 201
    assert core.api.handle(Request("POST", "/v1/consent", headers, body)).status == 401  # the same signed request: refused by the identity layer
    with pytest.raises(Exception) as e:  # and the store itself refuses a reused request id
        core.consent.enable(["documents"], "n-owner-mac-0001-" + headers["x-atlas-nonce"])
    assert getattr(e.value, "code", "") == "conflict"
    assert (
        len([r for r in core.designation.audit_log() if r["from_state"] == "not_configured" and r["to_state"] == "enabled"]) == 1
    )  # enabled once (the worker may also audit having seen the OS permission)


def test_withdrawing_a_grant_purges_the_index_and_what_tasks_derived_and_a_second_withdrawal_is_not_found(world):
    core = world.build()
    core.start()
    world.os.set("documents", "granted")
    admin = owner(world)
    grant = admin.enable(["documents"])["grants"][0]["grant_id"]
    world.wait_indexed(core)
    answer_client = world.client()
    task = answer_client.ask(*world.question("en-total"))
    answer_client.result(task)
    after = admin.withdraw(grant)
    assert after["grants"][0]["revoked"] is True and core.indexes["documents"].coverage()["total"] == 0
    assert core.tasks.answer(task)["citations"] == []
    with pytest.raises(atlas_client.ClientError) as e:
        admin.withdraw(grant)
    assert e.value.code == "not_found"
    with pytest.raises(atlas_client.ClientError) as e:
        admin.withdraw("grant-unknown-1")
    assert e.value.code == "not_found"


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{",
        b"[]",
        b'{"sources":[]}',
        b'{"sources":["documents","documents"]}',
        b'{"sources":["finance"]}',
        b'{"sources":["health"]}',
        b'{"sources":["mail_attachment"]}',
        b'{"sources":["nope"]}',
        b'{"sources":["documents"],"x":1}',
        b'{"sources":[1]}',
    ],
)
def test_a_malformed_or_undesignable_choice_changes_nothing(world, body):
    core = world.build()
    core.start()
    world.os.set("documents", "granted")
    response = call(core, world, world.owner_key, OWNER, "POST", "/v1/consent", body)
    assert response.status == 400 and json.loads(response.body)["code"] == "invalid_request"
    assert core.designation.latest_grants(core.designation.designable()) == [] and core.designation.audit_log() == []


def test_a_revoked_owner_client_loses_the_power_to_change_consent(world):
    core = world.build()
    core.start()
    world.clients.revoke(OWNER)
    with pytest.raises(atlas_client.ClientError) as e:
        owner(world).consent()
    assert e.value.code == "forbidden"


def test_the_response_carries_the_version_echo_and_unsigned_calls_are_refused(world):
    core = world.build()
    core.start()
    ok = call(core, world, world.owner_key, OWNER, "GET", "/v1/consent")
    assert ok.status == 200 and ok.headers["x-atlas-api-version"] == "1.1"
    assert core.api.handle(Request("GET", "/v1/consent", {"x-atlas-api-version": "1.1"}, b"")).status == 401
    time.sleep(0)


def test_delete_is_refused_everywhere_except_on_a_consent_grant(world):
    core = world.build()
    core.start()
    for target in ("/v1/tasks/aaaaaaaa", "/v1/tasks", "/v1/consent", "/v1/index/status", "/v1/version"):
        assert call(core, world, world.owner_key, OWNER, "DELETE", target, version="1.1" if target != "/v1/version" else "1.0").status in (400, 404), target


# ---- the owner's model mode (G-020: the deep tier only when the owner selects Research) ----------------------------------------------------------------------------------------
def test_only_an_owner_client_selects_the_model_mode_it_starts_as_default_and_the_gateway_follows_it(world):
    core = world.build()
    core.start()
    admin, plain = owner(world), world.client()
    assert admin.mode() == "default" and core.gateway._signals().mode == "default"
    assert admin.set_mode("research") == "research" and admin.mode() == "research" and core.gateway._signals().mode == "research"
    for action in (plain.mode, lambda: plain.set_mode("research")):
        with pytest.raises(atlas_client.ClientError) as e:
            action()
        assert e.value.code == "forbidden"
    assert admin.set_mode("default") == "default" and core.gateway._signals().mode == "default"


@pytest.mark.parametrize("payload", [b"", b"{", b"[]", b'{"mode":"turbo"}', b'{"mode":1}', b'{"mode":"research","x":1}', b"{}"])
def test_a_bad_mode_request_changes_nothing(world, payload):
    core = world.build()
    core.start()
    assert call(core, world, world.owner_key, OWNER, "POST", "/v1/mode", payload).status == 400
    assert core.mode.get() == "default"


def test_the_mode_is_a_1_1_route_and_resets_to_default_when_the_core_restarts(world):
    core = world.build()
    core.start()
    assert call(core, world, world.owner_key, OWNER, "GET", "/v1/mode", version="1.0").status == 404
    owner(world).set_mode("research")
    core.close()
    again = world.build()
    again.start()
    assert owner(world).mode() == "default"  # the deep tier is never on after a restart by accident


class _Index:
    def __init__(self, newest_ts):
        self.newest_ts = newest_ts

    def coverage(self):
        return {"searched": 1, "total": 1, "pending": 0, "scan_complete": True, "paused": None, "failed_reasons": {}, "newest_ts": self.newest_ts}


class _Access:
    """Permitted per source; `withdraw_after_read` withdraws a source between its first check and the re-check after its coverage was read."""

    def __init__(self, withdraw_after_read=()):
        self.checks, self.withdraw = {}, set(withdraw_after_read)

    def permitted(self, source_type):
        self.checks[source_type] = self.checks.get(source_type, 0) + 1
        return not (source_type in self.withdraw and self.checks[source_type] > 1)


def test_newest_indexed_compares_times_as_numbers_and_never_reports_a_source_withdrawn_while_it_was_read():
    """UC-L26 (review 6097009203): within one UTC second a whole-second time and a later fractional one are ordered by value, not by their text;
    and a source withdrawn while its coverage was being read contributes nothing (no count, no timestamp)."""
    from atlas_core.consent import ConsentService
    from atlas_core.documents import iso_utc

    whole, later = 1_790_000_000.0, 1_790_000_000.25  # the same second: "...:20Z" sorts after "...:20.250000Z" as text
    assert iso_utc(whole) > iso_utc(later)  # the trap the string comparison fell into
    both = ConsentService(None, _Access(), {"documents": _Index(later), "mail": _Index(whole)}).index_status()
    assert both["newest_indexed"] == iso_utc(later) and both["indexed"] == 2
    raced = ConsentService(None, _Access(withdraw_after_read={"documents"}), {"documents": _Index(later), "mail": _Index(whole)}).index_status()
    assert raced["newest_indexed"] == iso_utc(whole) and raced["indexed"] == 1 and raced["total"] == 1
