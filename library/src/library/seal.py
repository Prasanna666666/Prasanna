"""Sealed boxes for what one container hands to another through a shared volume. The reader (the least trusted container) is given only a PUBLIC key: it can write a sealed file but can never read one, not even its own. Only the app that holds the private key can open it. X25519 key agreement, HKDF-SHA256, ChaCha20-Poly1305; a fresh ephemeral key for every file, so two seals of the same text differ."""

from __future__ import annotations

import os
import sys
from typing import Any

KEY_BYTES = 32
NONCE_BYTES = 12
_INFO = b"atlas-handover-v1"


def _lib() -> Any:
    """The `cryptography` pieces, imported only when a file is actually sealed or opened: an image that does not use the sealed hand-over does not need the library, and importing this module never fails for the lack of it."""
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError as error:
        raise SealUnavailableError(
            "the sealed hand-over needs the Python package `cryptography` (pip install cryptography), and it is not installed here"
        ) from error

    class Lib:
        pass

    lib = Lib()
    lib.InvalidTag, lib.hashes, lib.serialization = InvalidTag, hashes, serialization  # type: ignore[attr-defined]
    lib.Private, lib.Public, lib.Aead, lib.Hkdf = X25519PrivateKey, X25519PublicKey, ChaCha20Poly1305, HKDF  # type: ignore[attr-defined]
    return lib


class SealError(ValueError):
    """The file could not be opened with the key given: a wrong key and a damaged file cannot be told apart (the authentication fails the same way), so neither is a reason to throw the file away."""


class SealUnavailableError(RuntimeError):
    """The sealing library is not installed in this Python. Not a fault of any file or key: nothing is read, opened or deleted because of it."""


class SealKeyError(SealError):
    """The KEY is unusable: not hexadecimal, not 32 bytes, or empty. That is a configuration mistake of the person running it, never a fault of the file."""


class NotSealedError(SealError):
    """The file is too short to be a sealed file at all. That is a fault of the file, whatever key is given."""


def _key_bytes(hex_text: str, what: str) -> bytes:
    try:
        raw = bytes.fromhex(hex_text.strip())
    except (ValueError, AttributeError) as error:
        raise SealKeyError(f"the {what} key is not hexadecimal") from error
    if len(raw) != KEY_BYTES:
        raise SealKeyError(f"the {what} key must be {KEY_BYTES} bytes, not {len(raw)}")
    return raw


def _raw_public(lib: Any, key: Any) -> bytes:
    return bytes(key.public_bytes(lib.serialization.Encoding.Raw, lib.serialization.PublicFormat.Raw))


def generate_keypair() -> tuple[str, str]:
    """(private key, public key), each as hex. The private one stays with the app that reads; only the public one goes to the reader."""
    lib = _lib()
    private = lib.Private.generate()
    raw = private.private_bytes(lib.serialization.Encoding.Raw, lib.serialization.PrivateFormat.Raw, lib.serialization.NoEncryption())
    return bytes(raw).hex(), _raw_public(lib, private.public_key()).hex()


def public_from_private(private_hex: str) -> str:
    """The public key that belongs to a private key (so the Keychain needs to be given only the private one)."""
    lib = _lib()
    return _raw_public(lib, lib.Private.from_private_bytes(_key_bytes(private_hex, "private")).public_key()).hex()


def _key(lib: Any, shared: bytes, eph_public: bytes, recipient_public: bytes) -> bytes:
    return bytes(lib.Hkdf(algorithm=lib.hashes.SHA256(), length=KEY_BYTES, salt=eph_public + recipient_public, info=_INFO).derive(shared))


def seal(plaintext: bytes, public_hex: str) -> bytes:
    lib = _lib()
    recipient = _key_bytes(public_hex, "public")
    ephemeral = lib.Private.generate()
    eph_public = _raw_public(lib, ephemeral.public_key())
    key = _key(lib, ephemeral.exchange(lib.Public.from_public_bytes(recipient)), eph_public, recipient)
    nonce = os.urandom(NONCE_BYTES)
    return eph_public + nonce + bytes(lib.Aead(key).encrypt(nonce, plaintext, eph_public))


def open_sealed(blob: bytes, private_hex: str) -> bytes:
    if len(blob) < KEY_BYTES + NONCE_BYTES + 16:
        raise NotSealedError("too short to be a sealed file")
    lib = _lib()
    private = lib.Private.from_private_bytes(_key_bytes(private_hex, "private"))
    recipient_public = _raw_public(lib, private.public_key())
    eph_public, nonce, body = blob[:KEY_BYTES], blob[KEY_BYTES : KEY_BYTES + NONCE_BYTES], blob[KEY_BYTES + NONCE_BYTES :]
    try:
        shared = private.exchange(lib.Public.from_public_bytes(eph_public))
    except ValueError as error:  # a low-order or invalid ephemeral key: no honest sealer writes one, so this is a fault of the file whatever key is given
        raise NotSealedError("not a valid sealed file") from error
    key = _key(lib, shared, eph_public, recipient_public)
    try:
        return bytes(lib.Aead(key).decrypt(nonce, body, eph_public))
    except lib.InvalidTag as error:
        raise SealError("wrong key or damaged file") from error


def main(argv: list[str] | None = None) -> str | None:
    """`python3 library/src/library/seal.py`: prints a new key pair, private first, then public (the private one goes in the Keychain, only the public one to the reader). Returns a plain message when the sealing library is missing."""
    args = sys.argv[1:] if argv is None else argv
    try:
        if args[:1] == ["--public-from-private"] and len(args) == 2:  # noqa: PLR2004
            print(public_from_private(args[1]))
            return None
        print(*generate_keypair(), sep="\n")
    except SealKeyError as problem:
        return str(problem)
    except SealUnavailableError as problem:
        return f"{problem}\nRun: python3 -m venv /tmp/atlas-venv && source /tmp/atlas-venv/bin/activate && pip install cryptography   and try again (or use the Docker route in docs/MAC_VERIFICATION.md)."
    return None


if __name__ == "__main__":
    raise SystemExit(main())
