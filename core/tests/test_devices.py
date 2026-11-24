"""Stage 8 (Core side): pairing is an owner act with a single-use, short-lived, guess-limited code; the device can pin the Core; revocation is immediate, durable and total; no listener is opened."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.devices import MAX_WRONG_CODES, CoreIdentity, DeviceDirectory, DeviceError, verify_core
from atlas_core.errors import CoreError
from atlas_core.identity import ClientRegistry, sign_request

pytestmark = pytest.mark.criterion(14)
START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


class Rig:
    def __init__(self, tmp: Path) -> None:
        self.now = [START]
        self.registry = ClientRegistry(path=tmp / "clients.json")
        self.owner_key = Ed25519PrivateKey.generate()
        self.registry.register("owner-mac-0001", self.owner_key.public_key(), owner=True)
        self.identity = CoreIdentity(tmp / "identity.key")
        self.directory = DeviceDirectory(self.registry, self.identity, tmp / "devices.json", clock=lambda: self.now[0])
        self.tmp = tmp

    def pair(self, device_id="iphone-0001", label="Phone", offer=None):
        offer = offer or self.directory.open_offer("owner-mac-0001")
        key = Ed25519PrivateKey.generate()
        proof = self.directory.pair(offer.code, device_id, label, key.public_key(), "nonce-1")
        return offer, key, proof

    def request(self, client_id, key):
        headers = sign_request(key, client_id, "GET", "/v1/version", b"", self.now[0])
        return self.registry.verify("GET", "/v1/version", headers, b"", self.now[0])


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_only_an_owner_client_can_open_a_pairing_offer_and_a_paired_device_is_never_an_owner(rig):
    with pytest.raises(DeviceError) as e:
        rig.directory.open_offer("someone-else")
    assert e.value.code == "owner_only"
    offer, key, _ = rig.pair()
    assert rig.request("iphone-0001", key) == "iphone-0001" and rig.registry.is_owner("iphone-0001") is False
    assert rig.directory.devices()[0]["label"] == "Phone" and rig.directory.devices()[0]["revoked_at"] is None
    assert offer.code not in (rig.tmp / "devices.json").read_text() and offer.code not in (rig.tmp / "clients.json").read_text()  # the code is never stored


def test_a_code_works_once_expires_after_five_minutes_and_is_closed_by_guessing(rig):
    offer = rig.directory.open_offer("owner-mac-0001")
    rig.pair(offer=offer)
    with pytest.raises(DeviceError) as e:
        rig.directory.pair(offer.code, "second-0001", "Other", Ed25519PrivateKey.generate().public_key(), "n")
    assert e.value.code == "no_open_offer"  # single-use
    late = rig.directory.open_offer("owner-mac-0001")
    rig.now[0] += timedelta(minutes=5, seconds=1)
    with pytest.raises(DeviceError):
        rig.directory.pair(late.code, "late-0001", "Late", Ed25519PrivateKey.generate().public_key(), "n")
    fresh = rig.directory.open_offer("owner-mac-0001")
    for _ in range(MAX_WRONG_CODES):
        with pytest.raises(DeviceError) as bad:
            rig.directory.pair("wrong-code-guess", "guess-0001", "Guess", Ed25519PrivateKey.generate().public_key(), "n")
        assert bad.value.code == "no_open_offer"  # the same code for a wrong guess, an expired offer and a spent one
    with pytest.raises(DeviceError):
        rig.directory.pair(
            fresh.code, "guess-0001", "Guess", Ed25519PrivateKey.generate().public_key(), "n"
        )  # even the right code is refused now: the offer was closed
    assert not rig.registry.known("guess-0001")


def test_the_device_can_pin_the_core_and_rejects_an_impostor(rig):
    offer, device_key, proof = rig.pair()
    assert verify_core(offer.core_fingerprint, rig.identity.public_key, proof, device_key.public_key(), "nonce-1") is True
    impostor = CoreIdentity(rig.tmp / "other.key")
    forged = impostor.prove(device_key.public_key(), "nonce-1")
    assert verify_core(offer.core_fingerprint, impostor.public_key, forged, device_key.public_key(), "nonce-1") is False  # not the pinned key
    assert verify_core(offer.core_fingerprint, rig.identity.public_key, proof, device_key.public_key(), "other-nonce") is False  # not this exchange
    assert oct((rig.tmp / "identity.key").stat().st_mode & 0o777) == "0o600" and CoreIdentity(rig.tmp / "identity.key").fingerprint == rig.identity.fingerprint


def test_revocation_is_immediate_durable_and_survives_a_restart(rig):
    _, key, _ = rig.pair()
    assert rig.request("iphone-0001", key) == "iphone-0001"
    rig.directory.revoke("owner-mac-0001", "iphone-0001")
    with pytest.raises(CoreError) as e:
        rig.request("iphone-0001", key)
    assert e.value.code == "forbidden"
    reloaded = ClientRegistry(path=rig.tmp / "clients.json")  # a restart of the Core
    headers = sign_request(key, "iphone-0001", "GET", "/v1/version", b"", rig.now[0])
    with pytest.raises(CoreError) as e2:
        reloaded.verify("GET", "/v1/version", headers, b"", rig.now[0])
    assert e2.value.code == "forbidden" and DeviceDirectory(reloaded, rig.identity, rig.tmp / "devices.json").devices()[0]["revoked_at"] is not None


def test_a_member_cannot_revoke_anything_and_the_last_owner_cannot_be_revoked(rig):
    rig.pair()
    with pytest.raises(DeviceError) as e:
        rig.directory.revoke("iphone-0001", "owner-mac-0001")
    assert e.value.code == "owner_only"
    with pytest.raises(DeviceError) as e2:
        rig.directory.revoke("owner-mac-0001", "owner-mac-0001")
    assert e2.value.code == "last_owner" and rig.registry.is_owner("owner-mac-0001")
    with pytest.raises(DeviceError) as e3:
        rig.directory.revoke("owner-mac-0001", "nobody-0001")
    assert e3.value.code == "unknown_device"


def test_no_module_of_the_core_binds_an_internet_address_or_opens_a_public_port():
    src = Path(__file__).resolve().parents[1] / "src" / "atlas_core"
    for path in src.glob("*.py"):
        text = path.read_text()
        assert not re.search(r"AF_INET|AF_INET6|\.bind\(\(|0\.0\.0\.0|create_server|HTTPServer\(", text), (
            path.name
        )  # the Core serves one owner-only Unix socket; a remote channel is a seam in front of it
    assert "AF_UNIX" in (src / "transport.py").read_text()


def test_a_signed_request_used_before_a_restart_cannot_be_replayed_after_it(rig):
    """ATLAS-SEC-067: the used-nonce ledger survives a restart; a distinct fresh request still works; a concurrent duplicate is refused once."""
    _, key, _ = rig.pair()
    headers = sign_request(key, "iphone-0001", "GET", "/v1/version", b"", rig.now[0], nonce="captured-nonce-1")
    assert rig.registry.verify("GET", "/v1/version", headers, b"", rig.now[0]) == "iphone-0001"
    restarted = ClientRegistry(path=rig.tmp / "clients.json")  # the Core stops and starts again inside the timestamp window
    with pytest.raises(CoreError) as replay:
        restarted.verify("GET", "/v1/version", headers, b"", rig.now[0])
    assert replay.value.code == "unauthenticated"
    fresh = sign_request(key, "iphone-0001", "GET", "/v1/version", b"", rig.now[0], nonce="another-nonce")
    assert restarted.verify("GET", "/v1/version", fresh, b"", rig.now[0]) == "iphone-0001"
    later = rig.now[0] + timedelta(hours=1)  # once the window has passed the entry is dropped, so the ledger stays bounded
    import threading

    outcomes: list[str] = []
    twin = sign_request(key, "iphone-0001", "GET", "/v1/version", b"", later, nonce="twin")

    def go():
        try:
            outcomes.append(restarted.verify("GET", "/v1/version", twin, b"", later))
        except CoreError as error:
            outcomes.append(error.code)

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count("iphone-0001") == 1 and outcomes.count("unauthenticated") == 7
    assert oct((rig.tmp / "clients.nonces").stat().st_mode & 0o777) == "0o600"


def test_a_failed_durable_write_never_reports_a_revocation_or_pairing_as_done(rig, monkeypatch):
    """ATLAS-SEC-068 / ATLAS-DEV-041: the registry and device list are written with fsync and a directory fsync; any failure leaves the device neither listed nor able to sign, and a failed revoke raises."""
    import os as os_module

    from atlas_core import identity

    calls: list[str] = []
    real_fsync = os_module.fsync
    monkeypatch.setattr(identity.os, "fsync", lambda fd: (calls.append("fsync"), real_fsync(fd))[1])
    rig.pair("durable-phone")
    assert calls.count("fsync") >= 4  # temp file and folder, for the registry and for the device list

    key = Ed25519PrivateKey.generate()
    for failing in ("registry", "devices"):
        offer = rig.directory.open_offer("owner-mac-0001")
        real_write = identity.write_durably
        target = "clients.json" if failing == "registry" else "devices.json"

        def broken(path, text, real_write=real_write, target=target):
            if path.name == target:
                raise OSError("disk full")
            return real_write(path, text)

        monkeypatch.setattr(identity, "write_durably", broken)
        monkeypatch.setattr("atlas_core.devices.write_durably", broken)
        with pytest.raises(OSError):
            rig.directory.pair(offer.code, f"phone-{failing}", "Phone", key.public_key(), "n")
        monkeypatch.setattr(identity, "write_durably", real_write)
        monkeypatch.setattr("atlas_core.devices.write_durably", real_write)
        assert not rig.registry.known(f"phone-{failing}") and all(d["device_id"] != f"phone-{failing}" for d in rig.directory.devices())
        assert not ClientRegistry(path=rig.tmp / "clients.json").known(f"phone-{failing}")

    monkeypatch.setattr(identity, "write_durably", lambda path, text: (_ for _ in ()).throw(OSError("fsync failed")))
    with pytest.raises(OSError):
        rig.directory.revoke("owner-mac-0001", "durable-phone")  # the owner is told it did not complete
