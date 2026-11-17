"""Sealed boxes for what one container hands to another through a shared volume. The reader (the least trusted container) is given only a PUBLIC key: it can write a sealed file but can never read one, not even its own. Only the app that holds the private key can open it. X25519 key agreement, HKDF-SHA256, ChaCha20-Poly1305; a fresh ephemeral key for every file, so two seals of the same text differ."""

from __future__ import annotations

import os
from typing import Any

KEY_BYTES = 32
NONCE_BYTES = 12
_INFO = b"atlas-handover-v1"


def _lib() -> Any:
    """The `cryptography` pieces, imported only when a file is actually sealed or opened: an image that does not use the sealed hand-over does not need the library, and importing this module never fails for the lack of it."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    class Lib:
        pass

    lib = Lib()
    lib.InvalidTag, lib.hashes, lib.serialization = InvalidTag, hashes, serialization  # type: ignore[attr-defined]
    lib.Private, lib.Public, lib.Aead, lib.Hkdf = X25519PrivateKey, X25519PublicKey, ChaCha20Poly1305, HKDF  # type: ignore[attr-defined]
    return lib


class SealError(ValueError):
    """The file could not be opened: wrong key, damaged, or not a sealed file at all."""


def _raw_public(lib: Any, key: Any) -> bytes:
    return bytes(key.public_bytes(lib.serialization.Encoding.Raw, lib.serialization.PublicFormat.Raw))


def generate_keypair() -> tuple[str, str]:
    """(private key, public key), each as hex. The private one stays with the app that reads; only the public one goes to the reader."""
    lib = _lib()
    private = lib.Private.generate()
    raw = private.private_bytes(lib.serialization.Encoding.Raw, lib.serialization.PrivateFormat.Raw, lib.serialization.NoEncryption())
    return bytes(raw).hex(), _raw_public(lib, private.public_key()).hex()


def _key(lib: Any, shared: bytes, eph_public: bytes, recipient_public: bytes) -> bytes:
    return bytes(lib.Hkdf(algorithm=lib.hashes.SHA256(), length=KEY_BYTES, salt=eph_public + recipient_public, info=_INFO).derive(shared))


def seal(plaintext: bytes, public_hex: str) -> bytes:
    lib = _lib()
    recipient = bytes.fromhex(public_hex)
    ephemeral = lib.Private.generate()
    eph_public = _raw_public(lib, ephemeral.public_key())
    key = _key(lib, ephemeral.exchange(lib.Public.from_public_bytes(recipient)), eph_public, recipient)
    nonce = os.urandom(NONCE_BYTES)
    return eph_public + nonce + bytes(lib.Aead(key).encrypt(nonce, plaintext, eph_public))


def open_sealed(blob: bytes, private_hex: str) -> bytes:
    if len(blob) < KEY_BYTES + NONCE_BYTES + 16:
        raise SealError("too short to be a sealed file")
    lib = _lib()
    private = lib.Private.from_private_bytes(bytes.fromhex(private_hex))
    recipient_public = _raw_public(lib, private.public_key())
    eph_public, nonce, body = blob[:KEY_BYTES], blob[KEY_BYTES : KEY_BYTES + NONCE_BYTES], blob[KEY_BYTES + NONCE_BYTES :]
    key = _key(lib, private.exchange(lib.Public.from_public_bytes(eph_public)), eph_public, recipient_public)
    try:
        return bytes(lib.Aead(key).decrypt(nonce, body, eph_public))
    except lib.InvalidTag as error:
        raise SealError("wrong key or damaged file") from error


if (
    __name__ == "__main__"
):  # python -m library.seal : prints a new pair, private first, then public (store the private one in the Keychain, give only the public one to the reader)
    print(*generate_keypair(), sep="\n")
