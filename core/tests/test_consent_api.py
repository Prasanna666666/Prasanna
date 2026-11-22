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

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="peer credentials are only verified on Linux in this stage")
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
    assert status["state"] == "idle" and status["indexed"] == status["total"] > 0 and status["newest_indexed"] is None
    assert "1250.50" not in json.dumps(status) and "invoice" not in json.dumps(status)


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
