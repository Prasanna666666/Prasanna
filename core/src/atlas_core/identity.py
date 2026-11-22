"""Per-client identity: every request is signed with the client's own Ed25519 key. Nothing is trusted because it comes from localhost or carries an Origin header."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .errors import CoreError
from .rules import Rules, load_rules

H_CLIENT, H_TIME, H_NONCE, H_SIG, H_VERSION = "x-atlas-client", "x-atlas-timestamp", "x-atlas-nonce", "x-atlas-signature", "x-atlas-api-version"


def canonical(method: str, target: str, timestamp: str, nonce: str, body: bytes, version: str = "1.0") -> bytes:
    """The signed message: five fields for 1.0, six for 1.1 with the applied version first (CONTRACT_1_1.md, Signing). No field may contain CR or LF."""
    fields = [method.upper(), target, timestamp, nonce, hashlib.sha256(body).hexdigest()]
    if any("\r" in f or "\n" in f for f in fields):
        raise ValueError("line break in a signed field")
    return "\n".join(fields if version == "1.0" else [version, *fields]).encode()


def sign_request(  # noqa: PLR0913
    key: Ed25519PrivateKey, client_id: str, method: str, target: str, body: bytes, now: datetime, nonce: str | None = None, *, version: str = "1.0"
) -> dict[str, str]:
    """What a client sends (used by clients and by the tests). For 1.1 the version is signed and sent in the version header."""
    stamp, one_time = str(int(now.timestamp())), nonce or secrets.token_hex(12)
    signature = key.sign(canonical(method, target, stamp, one_time, body, version))
    out = {H_CLIENT: client_id, H_TIME: stamp, H_NONCE: one_time, H_SIG: base64.b64encode(signature).decode()}
    return out if version == "1.0" else {**out, H_VERSION: version}


@dataclass
class _Client:
    key: Ed25519PublicKey
    revoked: bool = False
    owner: bool = False  # an enrolled owner-interactive client: the only kind that may change consent


class NonceCache:
    """A nonce is accepted once within its time window; the cache is bounded by time."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl, self._seen, self._lock = ttl_seconds, OrderedDict[str, float](), threading.Lock()

    def first_use(self, key: str, now: float) -> bool:
        with self._lock:
            while self._seen and next(iter(self._seen.values())) < now - self._ttl:
                self._seen.popitem(last=False)
            if key in self._seen:
                return False
            self._seen[key] = now
            return True


class ClientRegistry:
    def __init__(self, rules: Rules | None = None) -> None:
        self._rules = rules or load_rules()
        self._clients: dict[str, _Client] = {}
        self._nonces = NonceCache(self._rules.limit("nonce_ttl_seconds"))

    def register(self, client_id: str, public_key: Ed25519PublicKey, *, owner: bool = False) -> None:
        self._clients[client_id] = _Client(public_key, owner=owner)

    def is_owner(self, client_id: str) -> bool:
        client = self._clients.get(client_id)
        return client is not None and client.owner and not client.revoked

    def revoke(self, client_id: str) -> None:
        if client_id in self._clients:
            self._clients[client_id].revoked = True

    def verify(self, method: str, target: str, headers: Mapping[str, str], body: bytes, now: datetime, version: str = "1.0") -> str:
        """The client id of a valid request. Raises CoreError('unauthenticated') for anything missing, wrong, stale or replayed, and 'forbidden' for a revoked client."""
        client_id, stamp, nonce, signature = (headers.get(h, "") for h in (H_CLIENT, H_TIME, H_NONCE, H_SIG))
        client = self._clients.get(client_id)
        if client is None or not (stamp and nonce and signature) or not self._fresh(stamp, now):
            raise CoreError("unauthenticated")
        try:
            client.key.verify(base64.b64decode(signature, validate=True), canonical(method, target, stamp, nonce, body, version))
        except (InvalidSignature, ValueError):
            raise CoreError("unauthenticated") from None
        if client.revoked:
            raise CoreError("forbidden")
        if not self._nonces.first_use(f"{client_id}:{nonce}", now.timestamp()):
            raise CoreError("unauthenticated")
        return client_id

    def _fresh(self, stamp: str, now: datetime) -> bool:
        try:
            return abs(now.timestamp() - int(stamp)) <= self._rules.limit("clock_skew_seconds")
        except ValueError:
            return False
