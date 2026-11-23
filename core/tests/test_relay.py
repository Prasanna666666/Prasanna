"""The remote channel: a relay that only ever listens on a private or VPN address, forwards only the contract's paths, adds no authority, and keeps first-owner enrolment local to the Mac."""

from __future__ import annotations

import http.client
import socket

import pytest
from conftest import KEY
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_client import atlas_client
from test_operations_api import OpsWorld

from atlas_core.relay import Relay, RelayRefused, permitted_bind

pytestmark = pytest.mark.criterion(11)


@pytest.mark.parametrize(
    "host, allowed",
    [
        ("127.0.0.1", True),
        ("10.1.2.3", True),
        ("172.16.0.9", True),
        ("192.168.1.20", True),
        ("169.254.10.10", True),
        ("100.64.0.1", True),  # a VPN's shared range (for example Tailscale)
        ("100.127.255.254", True),
        ("0.0.0.0", False),
        ("8.8.8.8", False),
        ("100.128.0.1", False),
        ("224.0.0.1", False),
        ("localhost", False),
        ("example.com", False),
        ("::1", False),
        ("", False),
    ],
)
def test_the_relay_will_only_listen_on_a_private_or_vpn_address(host, allowed, tmp_path):
    assert permitted_bind(host) is allowed
    if not allowed:
        with pytest.raises(RelayRefused) as e:
            Relay(host, 0, tmp_path / "s.sock")  # refused before any socket is opened
        assert e.value.code == "address_not_private"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    world = OpsWorld(tmp_path / "a")
    world.build().start()
    relay = Relay("127.0.0.1", 0, world.sock)
    relay.start()
    port = relay.server_address[1]

    class Tcp(http.client.HTTPConnection):
        def __init__(self, _path, timeout=10):
            super().__init__("127.0.0.1", port, timeout=timeout)

    monkeypatch.setattr(atlas_client, "_Unix", Tcp)
    yield world, relay, port
    relay.close()
    world.close()


def test_a_signed_request_through_the_relay_is_answered_exactly_as_on_the_mac_and_a_stranger_is_refused(rig):
    world, _relay, _port = rig
    assert world.client().consent()["grants"] == []  # the owner's signed request, over TCP
    stranger = atlas_client.AtlasClient("ignored", Ed25519PrivateKey.generate(), "stranger-client-0001", clock=world.clock)
    with pytest.raises(atlas_client.ClientError) as e:
        stranger.consent()
    assert e.value.code == "unauthenticated"  # the relay adds no authority: the Core still checks every signature


def test_the_relay_forwards_only_the_contract_and_never_the_first_owner_enrolment_or_anything_malformed(rig):
    _world, _relay, port = rig

    def raw(payload: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(payload)
            data = b""
            try:
                while chunk := s.recv(4096):
                    data += chunk
            except (TimeoutError, ConnectionResetError):
                pass
            return data

    enrol = raw(b"POST /v1/enrol HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n{}")
    assert enrol.startswith(b"HTTP/1.1 403")  # first-owner enrolment is local to the Mac
    assert raw(b"GET /etc/passwd HTTP/1.1\r\nHost: x\r\n\r\n").startswith(b"HTTP/1.1 403")
    assert raw(b"GET /v1/../v1/enrol HTTP/1.1\r\nHost: x\r\n\r\n").startswith(b"HTTP/1.1 403")
    assert raw(b"POST /v1/sync HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n").startswith(b"HTTP/1.1 400")
    assert raw(b"POST /v1/sync HTTP/1.1\r\nHost: x\r\nContent-Length: 99999999\r\n\r\n").startswith(b"HTTP/1.1 400")
    assert raw(b"GARBAGE\r\n\r\n").startswith(b"HTTP/1.1 400")
    assert raw(b"GET /v1/version HTTP/1.1\r\nHost: x\r\n\r\n").startswith(
        b"HTTP/1.1 401"
    )  # a contract path reaches the Core, which refuses an unsigned request itself


def test_a_phone_pairs_and_syncs_through_the_relay_and_removing_it_ends_its_access(rig):
    world, _relay, _port = rig
    owner = world.client()
    offer = owner.open_pairing_offer()
    key = Ed25519PrivateKey.generate()
    from atlas_core.devices import verify_core

    device = atlas_client.AtlasClient("ignored", key, "phone-over-relay-0001", clock=world.clock)
    import base64

    public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    result = device.pair_device(offer["code"], "phone-over-relay-0001", "Test phone", public, "nonce-0123456789abcdef")
    assert verify_core(offer["core_fingerprint"], _public(result["core_public_key"]), _raw(result["proof"]), key.public_key(), "nonce-0123456789abcdef")
    assert device.sync([]) == []
    owner.revoke_device("phone-over-relay-0001")
    with pytest.raises(atlas_client.ClientError) as e:
        device.sync([])
    assert e.value.code == "forbidden"
    assert KEY  # synthetic fixtures only


def _raw(text):
    import base64

    return base64.b64decode(text)


def _public(text):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    return Ed25519PublicKey.from_public_bytes(_raw(text))


def test_the_relays_body_cap_is_the_apis_own():
    from atlas_core import api, relay

    assert relay.MAX_BODY_BYTES == api.MAX_BODY_BYTES
