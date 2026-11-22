"""Blocker 4 (review 6011238976): a fresh install can enrol its owner client without any out-of-band step, once, durably, and nothing else can take that place afterwards."""

from __future__ import annotations

import base64
import json
import os
import stat
import sys
import threading

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_app import World, atlas_client

from atlas_core import contracts
from atlas_core.api import Request
from atlas_core.identity import sign_request

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="peer credentials are only verified on Linux in this stage")


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path, durable_clients=True, bootstrap_code=CODE)
    yield w
    w.close()


CODE = "first-run-code-0123456789abcdef"


def body(client_id="owner-fresh-0001", key=None, role="owner", code=CODE):
    key = key or Ed25519PrivateKey.generate().public_key()
    out = {"client_id": client_id, "public_key": base64.b64encode(key.public_bytes_raw()).decode(), "role": role}
    return {**out, "bootstrap_code": code} if code else out


def post(core, payload, signer=None, version="1.1"):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = (
        sign_request(signer[0], signer[1], "POST", "/v1/enrol", raw, core.clock(), version=version)
        if signer
        else ({"x-atlas-api-version": version} if version else {})
    )
    return core.api.handle(Request("POST", "/v1/enrol", headers, raw))


def test_a_fresh_install_enrols_its_owner_client_unsigned_once_and_can_then_act_as_owner(world):
    core = world.build()
    path = core.start()
    key = Ed25519PrivateKey.generate()
    client = atlas_client.AtlasClient(path, key, "owner-fresh-0001", clock=world.clock)
    with pytest.raises(atlas_client.ClientError) as before:  # not enrolled yet: nothing it signs is accepted
        client.consent()
    assert before.value.code == "unauthenticated"
    answer = client.enrol_self(bootstrap_code=CODE)
    contracts.validate("EnrolResponse", answer, "1.1")
    assert answer == {"client_id": "owner-fresh-0001", "role": "owner"}
    assert client.consent()["grants"] == []  # and it is an OWNER client: the consent route answers


def test_the_first_run_window_closes_after_one_enrolment_and_a_second_unsigned_attempt_is_refused(world):
    core = world.build()
    core.start()
    assert post(core, body("owner-fresh-0001")).status == 201
    for attempt in (body("intruder-0000001"), body("owner-fresh-0001"), body("intruder-0000002", code=None)):
        refused = post(core, attempt)
        assert refused.status == 401 and json.loads(refused.body)["code"] == "unauthenticated"
    assert core.clients.has_owner() and not core.clients.is_owner("intruder-0000001")


def test_racing_first_run_callers_cannot_both_become_owner(world):
    core = world.build()
    results: list[int] = []

    def go(n):
        results.append(post(core, body(f"racer-client-{n:03d}")).status)

    threads = [threading.Thread(target=go, args=(n,)) for n in range(12)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert results.count(201) == 1 and set(results) <= {201, 401, 409}
    assert sum(core.clients.is_owner(f"racer-client-{n:03d}") for n in range(12)) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{",
        b"[]",
        {"client_id": "short", "public_key": "x", "role": "owner"},
        {**body(), "role": "member"},  # a member cannot be the first client
        {**body(), "role": "admin"},
        {**body(), "extra": 1},
        {**body(), "public_key": base64.b64encode(b"\x01" * 31).decode()},
        {**body(), "public_key": "!" * 44},
        {"client_id": "owner-fresh-0001"},
    ],
)
def test_a_malformed_first_run_request_enrols_nobody(world, payload):
    core = world.build()
    core.start()
    response = post(core, payload)
    assert response.status == 400 and json.loads(response.body)["code"] == "invalid_request" and not core.clients.has_owner()


def test_enrolment_is_a_1_1_route_only(world):
    core = world.build()
    for version in ("1.0", None):  # unsigned, not 1.1: the ordinary path applies and refuses it (no first-run window outside 1.1)
        assert post(core, body(), version=version).status == 401
    assert not core.clients.has_owner()
    other = Ed25519PrivateKey.generate()
    core.clients.register("known-client-001", other.public_key())
    assert post(core, body("owner-fresh-0001"), signer=(other, "known-client-001"), version="1.0").status == 404  # signed as 1.0: the route does not exist


def test_an_owner_client_enrols_a_member_with_a_signed_call_and_only_as_a_member(world):
    core = world.build()
    path = core.start()
    owner_key = Ed25519PrivateKey.generate()
    owner = atlas_client.AtlasClient(path, owner_key, "owner-fresh-0001", clock=world.clock)
    owner.enrol_self(bootstrap_code=CODE)
    member_key = Ed25519PrivateKey.generate()
    assert owner.enrol("member-device-001", member_key.public_key())["role"] == "member"
    member = atlas_client.AtlasClient(path, member_key, "member-device-001", clock=world.clock)
    assert member.index_status()["state"] in ("idle", "building")  # may read ordinary things
    with pytest.raises(atlas_client.ClientError) as e:
        member.consent()  # but is not an owner client
    assert e.value.code == "forbidden"
    with pytest.raises(atlas_client.ClientError) as e:
        member.enrol("another-device-02", Ed25519PrivateKey.generate().public_key())
    assert e.value.code == "forbidden"
    with pytest.raises(atlas_client.ClientError) as e:
        owner.enrol("third-device-0003", Ed25519PrivateKey.generate().public_key(), role="owner")  # an owner client cannot mint another owner
    assert e.value.code == "invalid_request"
    with pytest.raises(atlas_client.ClientError) as e:
        owner.enrol("member-device-001", Ed25519PrivateKey.generate().public_key())  # the id is taken
    assert e.value.code == "conflict" and not core.clients.is_owner("member-device-001")


def test_the_registry_survives_a_restart_stays_closed_and_holds_public_keys_only(world):
    core = world.build()
    core.start()
    key = Ed25519PrivateKey.generate()
    assert post(core, body("owner-fresh-0001", key.public_key())).status == 201
    core.close()
    again = world.build()
    again.start()
    assert again.clients.is_owner("owner-fresh-0001")
    assert post(again, body("intruder-0000001")).status == 401  # still closed after the restart
    file = world.tmp / "core" / "clients.json"
    assert stat.S_IMODE(os.stat(file).st_mode) == 0o600
    text = file.read_text()
    assert key.private_bytes_raw().hex() not in text and base64.b64encode(key.private_bytes_raw()).decode() not in text
    assert json.loads(text)["owner-fresh-0001"]["owner"] is True


def test_the_registry_itself_refuses_a_second_first_owner_even_if_a_caller_skipped_the_check(world):
    registry = world.build().clients
    first, second = Ed25519PrivateKey.generate().public_key(), Ed25519PrivateKey.generate().public_key()
    assert registry.enrol_first_owner("owner-fresh-0001", first) is True
    assert registry.enrol_first_owner("another-owner-01", second) is False  # no owner may be added through the first-run door once one exists
    assert (
        registry.enrol_first_owner("owner-fresh-0001", second) is False and registry.is_owner("owner-fresh-0001") and not registry.is_owner("another-owner-01")
    )


# ---- the first-run code: only the process that started the Core can enrol (the answer to "any process of this user can reach the socket") -----------------------------------
def test_a_program_that_reaches_the_socket_but_does_not_know_the_code_cannot_enrol(world):
    core = world.build()
    core.start()
    for attempt in (
        body("intruder-0000001", code=None),
        body("intruder-0000001", code="wrong-code-wrong-code-0000"),
        body("intruder-0000001", code=CODE[:-1] + "X"),
    ):
        refused = post(core, attempt)
        assert refused.status == 401 and json.loads(refused.body)["code"] == "unauthenticated"
    assert not core.clients.has_owner()
    assert post(core, body("owner-fresh-0001")).status == 201  # the legitimate app still can: the wrong guesses did not use up the code


def test_guessing_is_limited_the_gate_shuts_after_a_few_wrong_tries_even_for_the_right_code(world):
    core = world.build()
    core.start()
    for n in range(5):
        assert post(core, body(f"guesser-client-{n:02d}", code=f"guess-guess-guess-{n:04d}")).status == 401
    assert post(core, body("owner-fresh-0001")).status == 401 and not core.clients.has_owner()  # locked until the Core restarts


def test_the_code_is_checked_in_constant_time_hashed_never_stored_and_never_logged(world, caplog):
    import inspect

    from atlas_core import identity

    source = inspect.getsource(identity.BootstrapGate)
    assert "compare_digest" in source and "self._code" not in source
    core = world.build()
    core.start()
    post(core, body("intruder-0000001", code="wrong-code-wrong-code-0000"))
    post(core, body("owner-fresh-0001"))
    seen = "\n".join(r.getMessage() for r in caplog.records)
    assert CODE not in seen and "wrong-code-wrong-code-0000" not in seen
    assert CODE not in (world.tmp / "core" / "clients.json").read_text()


def test_the_code_is_used_up_by_the_first_success_and_a_restart_needs_no_code_once_an_owner_exists(world):
    core = world.build()
    core.start()
    assert post(core, body("owner-fresh-0001")).status == 201
    assert post(core, body("second-owner-001")).status == 401  # window closed, and the code is spent
    core.close()
    again = world.build()  # an owner exists: the Core starts without needing a code
    again.start()
    assert again.clients.is_owner("owner-fresh-0001")


def test_a_core_with_no_owner_and_no_code_refuses_to_start_unless_development_mode_is_explicit(tmp_path):
    w = World(tmp_path, durable_clients=True, bootstrap_code=None)
    w.bootstrap_code = None
    try:
        from atlas_core.app import Core, CoreConfig

        config = CoreConfig(
            data_dir=tmp_path / "core2", socket_path=w.sock, task_key="t" * 40, designation_key="d" * 40, documents_key="o" * 40, mail_key="m" * 40, anchor=w.anchor,
            os_permissions=w.os, manifest=w.manifest, model_record_key=b"k" * 32, runtime=w.runtime, documents=None, mailbox=None, clock=w.clock,
        )  # fmt: skip
        with pytest.raises(ValueError, match="bootstrap code"):
            Core(config)
        config.open_bootstrap = True
        Core(config).close()
    finally:
        w.close()


def test_a_too_short_code_is_refused():
    from atlas_core.identity import BootstrapGate

    with pytest.raises(ValueError, match="short"):
        BootstrapGate("short")
