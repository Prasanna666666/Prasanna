"""What the reader hands over can be sealed to a public key: the reader can write it and never read it back; only the holder of the private key can (review item O-16)."""

import pytest

from library import seal


def test_a_sealed_file_opens_with_the_private_key_and_hides_its_text():
    private, public = seal.generate_keypair()
    blob = seal.seal(b'{"text": "Glucose 5,2 mmol/L Alex Example"}', public)
    assert b"Glucose" not in blob and b"Alex" not in blob
    assert seal.open_sealed(blob, private) == b'{"text": "Glucose 5,2 mmol/L Alex Example"}'


def test_the_public_key_cannot_open_it_and_a_wrong_private_key_cannot_either():
    _, public = seal.generate_keypair()
    other_private, _ = seal.generate_keypair()
    blob = seal.seal(b"secret", public)
    with pytest.raises(seal.SealError):
        seal.open_sealed(blob, other_private)
    with pytest.raises((seal.SealError, ValueError)):
        seal.open_sealed(blob, public)  # what the reader holds is not enough to read


def test_a_damaged_or_truncated_file_is_refused():
    private, public = seal.generate_keypair()
    blob = bytearray(seal.seal(b"secret text", public))
    blob[-1] ^= 1
    with pytest.raises(seal.SealError):
        seal.open_sealed(bytes(blob), private)
    with pytest.raises(seal.SealError):
        seal.open_sealed(b"short", private)


def test_two_seals_of_the_same_text_differ():
    _, public = seal.generate_keypair()
    assert seal.seal(b"same", public) != seal.seal(b"same", public)
