"""Device pairing and revocation for remote clients (Stage 8; the iPhone client is a later, separate build, this is the Core side it will use).

* **Pairing is an owner act.** Only an enrolled OWNER client can open a pairing offer. The offer is a single-use code that lives five minutes; only its hash is kept; five wrong guesses close it. A device that
  presents the code and its public key is registered as an ordinary (member) client, never an owner.
* **The device can check the Core.** The offer carries the fingerprint of the Core's identity key. The Core signs the pairing transcript (the device's key, a nonce) with that key, so a device that pinned the
  fingerprint rejects an impostor in the middle. The identity key is created once, in the Core's own folder (mode 0600).
* **Revocation is immediate, durable and total.** A revoked device's signed requests are refused (`forbidden`) from the next request on, and the revocation survives a restart. The last owner client cannot be
  revoked (that would lock the owner out of their own Atlas), and a member can revoke nothing.
* **No public ports.** This module opens no listener and nothing in the Core binds an Internet address: the Core serves the owner-only Unix socket, and any remote channel is a separate, owner-controlled
  relay or VPN seam in front of it that must present a device signature like any other client.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from .identity import ClientRegistry

OFFER_TTL = timedelta(minutes=5)
MAX_WRONG_CODES = 5


class DeviceError(Exception):
    """A pairing or revocation step was refused. Carries a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Offer:
    code: str  # shown once to the owner (a QR code on the Mac); never stored in the clear
    core_fingerprint: str
    expires_at: datetime


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class CoreIdentity:
    """The Core's own Ed25519 identity key, created once and kept in its folder."""

    def __init__(self, path: Path) -> None:
        if path.exists():
            self._key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(path.read_text()))
        else:
            self._key = Ed25519PrivateKey.from_private_bytes(secrets.token_bytes(32))
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(base64.b64encode(self._key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode())

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self._key.public_key().public_bytes_raw()).hexdigest()

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._key.public_key()

    def prove(self, device_key: Ed25519PublicKey, nonce: str) -> bytes:
        return self._key.sign(device_key.public_bytes_raw() + nonce.encode())


def verify_core(pinned_fingerprint: str, core_public_key: Ed25519PublicKey, proof: bytes, device_key: Ed25519PublicKey, nonce: str) -> bool:
    """Run by the DEVICE: the key the Core presented must hash to the fingerprint pinned from the offer, and must have signed this device's key and nonce."""
    if not hmac.compare_digest(hashlib.sha256(core_public_key.public_bytes_raw()).hexdigest(), pinned_fingerprint):
        return False
    try:
        core_public_key.verify(proof, device_key.public_bytes_raw() + nonce.encode())
    except InvalidSignature:
        return False
    return True


class DeviceDirectory:
    def __init__(self, registry: ClientRegistry, identity: CoreIdentity, path: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._registry, self._identity, self._path, self._clock = registry, identity, path, clock
        self._lock = threading.Lock()
        self._offer: tuple[str, datetime, int] | None = None  # (code hash, expiry, wrong guesses)
        self._devices: dict[str, dict[str, str | None]] = json.loads(path.read_text()) if path.exists() else {}

    def _save(self) -> None:
        temporary = self._path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(self._devices, handle)
        temporary.replace(self._path)

    def open_offer(self, by_client: str) -> Offer:
        if not self._registry.is_owner(by_client):
            raise DeviceError("owner_only")
        code = secrets.token_urlsafe(12)
        expires = self._clock() + OFFER_TTL
        with self._lock:
            self._offer = (_hash(code), expires, 0)  # a new offer replaces any open one
        return Offer(code, self._identity.fingerprint, expires)

    def pair(self, code: str, device_id: str, label: str, device_key: Ed25519PublicKey, nonce: str) -> bytes:
        """Register a device and return the Core's proof for it to verify. Every refusal is the same code, so a guess learns nothing."""
        with self._lock:
            offer = self._offer
            if offer is None or offer[1] < self._clock() or offer[2] >= MAX_WRONG_CODES:
                raise DeviceError("no_open_offer")
            if not hmac.compare_digest(_hash(code), offer[0]):
                self._offer = (offer[0], offer[1], offer[2] + 1)
                raise DeviceError("no_open_offer")
            self._offer = None  # single-use
            if not self._registry.enrol(device_id, device_key):
                raise DeviceError("no_open_offer")
            self._devices[device_id] = {"label": label[:60], "paired_at": self._clock().isoformat(), "revoked_at": None}
            self._save()
        return self._identity.prove(device_key, nonce)

    def devices(self) -> list[dict[str, str | None]]:
        return [{"device_id": i, **d} for i, d in sorted(self._devices.items())]

    def revoke(self, by_client: str, device_id: str) -> None:
        with self._lock:
            if not self._registry.is_owner(by_client):
                raise DeviceError("owner_only")
            if not self._registry.known(device_id):
                raise DeviceError("unknown_device")
            if self._registry.is_owner(device_id) and self._registry.owner_count() <= 1:
                raise DeviceError("last_owner")  # revoking it would lock the owner out of their own Atlas
            self._registry.revoke(device_id)
            if device_id in self._devices:
                self._devices[device_id]["revoked_at"] = self._clock().isoformat()
                self._save()
