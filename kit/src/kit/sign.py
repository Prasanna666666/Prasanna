"""Calls between the platform's own programs are signed, so another program on this computer cannot use a service's port.

Atlas (and every app that calls another) signs `method + path + time` with a secret all of them share (kept in the macOS Keychain, handed to each
container at start). A service that has the secret refuses a request without a fresh, valid signature. Without the secret nothing is checked (a
throwaway or test run)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time

HEADER = "X-Platform-Sig"
WINDOW_SECONDS = 60


def key() -> bytes | None:
    value = os.environ.get("PLATFORM_KEY", "")
    return value.encode() if value else None


def _mac(secret: bytes, method: str, path: str, stamp: int) -> str:
    return hmac.new(secret, f"{method.upper()}\n{path}\n{stamp}".encode(), hashlib.sha256).hexdigest()


def sign(method: str, path: str, secret: bytes | None = None, now: float | None = None) -> dict[str, str]:
    """The header to send, or nothing when there is no secret."""
    secret = secret if secret is not None else key()
    if secret is None:
        return {}
    stamp = int(now if now is not None else time.time())
    return {HEADER: f"{stamp}.{_mac(secret, method, path, stamp)}"}


def valid(method: str, path: str, header: str | None, secret: bytes | None = None, now: float | None = None) -> bool:
    """True when there is no secret to check against, or the header is a fresh signature of this method and path."""
    secret = secret if secret is not None else key()
    if secret is None:
        return True
    try:
        stamp_text, _, given = (header or "").partition(".")
        stamp = int(stamp_text)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - stamp) > WINDOW_SECONDS:
        return False
    return hmac.compare_digest(given.encode(), _mac(secret, method, path, stamp).encode())
