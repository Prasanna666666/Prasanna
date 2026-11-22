"""Stage 7: signed update, atomic install, automatic rollback; the data folder is never touched."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.updater import Installer, UpdateError, parse_version, verify_release

pytestmark = pytest.mark.criterion(15)
KEY = Ed25519PrivateKey.generate()


def bundle(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()


def release(version: str, artefact: bytes, key: Ed25519PrivateKey = KEY):
    manifest = json.dumps({"version": version, "sha256": hashlib.sha256(artefact).hexdigest(), "size": len(artefact)}).encode()
    return verify_release(manifest, key.sign(manifest), KEY.public_key())


def good(version: str, tag: bytes = b"ok") -> tuple:
    art = bundle({"Atlas.app/Contents/MacOS/Atlas": tag, "Atlas.app/Contents/Info.plist": version.encode()})
    return release(version, art), art


def test_a_signed_update_installs_atomically_and_keeps_the_previous_version(tmp_path):
    inst = Installer(tmp_path)
    r1, a1 = good("1.0.0")
    assert inst.install(r1, a1, lambda p: (p / "Atlas.app/Contents/MacOS/Atlas").exists()) == "1.0.0" and inst.current_version() == "1.0.0"
    r2, a2 = good("1.1.0", b"new")
    assert inst.install(r2, a2, lambda p: True) == "1.1.0" and inst.current_version() == "1.1.0"
    assert (tmp_path / "versions" / "1.0.0").is_dir() and (tmp_path / "previous").resolve().name == "1.0.0"  # the old one is still there
    assert (tmp_path / "current" / "Atlas.app/Contents/MacOS/Atlas").read_bytes() == b"new"


def test_an_unsigned_wrongly_signed_or_altered_release_is_refused_before_anything_is_unpacked(tmp_path):
    art = bundle({"a": b"x"})
    manifest = json.dumps({"version": "9.9.9", "sha256": hashlib.sha256(art).hexdigest(), "size": len(art)}).encode()
    attacker = Ed25519PrivateKey.generate()
    with pytest.raises(UpdateError) as e:
        verify_release(manifest, attacker.sign(manifest), KEY.public_key())
    assert e.value.code == "bad_signature"
    with pytest.raises(UpdateError) as e2:
        verify_release(manifest.replace(b"9.9.9", b"9.9.8"), KEY.sign(manifest), KEY.public_key())  # altered after signing
    assert e2.value.code == "bad_signature"
    inst = Installer(tmp_path)
    r, _ = good("1.0.0")
    with pytest.raises(UpdateError) as e3:
        inst.install(r, bundle({"evil": b"y"}), lambda p: True)  # an artefact that is not the one the manifest names
    assert e3.value.code == "artefact_does_not_match_manifest" and inst.current_version() is None and not list((tmp_path / "versions").iterdir())


@pytest.mark.parametrize(
    ("manifest", "code"),
    [
        (b"not json", "bad_manifest"),
        (json.dumps({"version": "x", "sha256": "0" * 64, "size": 1}).encode(), "bad_version"),
        (json.dumps({"version": "1.0.0", "sha256": "zz", "size": 1}).encode(), "bad_manifest"),
        (json.dumps({"version": "1.0.0", "sha256": "0" * 64, "size": 0}).encode(), "bad_manifest"),
    ],
)
def test_a_malformed_manifest_is_a_code(manifest, code):
    with pytest.raises(UpdateError) as e:
        verify_release(manifest, KEY.sign(manifest), KEY.public_key())
    assert e.value.code == code


def test_never_backwards_by_accident_and_a_version_is_never_overwritten(tmp_path):
    inst = Installer(tmp_path)
    r2, a2 = good("1.1.0")
    inst.install(r2, a2, lambda p: True)
    for older in ("1.0.0", "1.1.0"):
        r, a = good(older, b"other")
        with pytest.raises(UpdateError) as e:
            inst.install(r, a, lambda p: True)
        assert e.value.code == "not_newer"
    assert parse_version("1.10.0") > parse_version("1.9.9") and inst.current_version() == "1.1.0"


def test_an_unhealthy_new_version_rolls_back_by_itself_and_the_data_folder_is_untouched(tmp_path):
    data = tmp_path / "Application Support" / "core"
    data.mkdir(parents=True)
    (data / "tasks.db").write_bytes(b"owner data")
    before = hashlib.sha256((data / "tasks.db").read_bytes()).hexdigest()
    inst = Installer(tmp_path / "app")
    r1, a1 = good("1.0.0")
    inst.install(r1, a1, lambda p: True)
    r2, a2 = good("1.1.0", b"broken")
    with pytest.raises(UpdateError) as e:
        inst.install(r2, a2, lambda p: (p / "Atlas.app/Contents/MacOS/Atlas").read_bytes() != b"broken")
    assert e.value.code == "unhealthy_rolled_back" and inst.current_version() == "1.0.0"
    assert hashlib.sha256((data / "tasks.db").read_bytes()).hexdigest() == before and sorted(p.name for p in data.iterdir()) == ["tasks.db"]


def test_a_crash_while_unpacking_leaves_the_old_version_current_and_no_half_version(tmp_path):
    inst = Installer(tmp_path)
    r1, a1 = good("1.0.0")
    inst.install(r1, a1, lambda p: True)
    r2, _ = good("1.1.0")
    corrupt = a1[: len(a1) // 2]  # a truncated archive that nevertheless matches a (forged) hash would still fail to unpack
    forged = release("1.1.0", corrupt)
    with pytest.raises(UpdateError) as e:
        inst.install(forged, corrupt, lambda p: True)
    assert e.value.code == "bad_artefact" and inst.current_version() == "1.0.0" and not (tmp_path / "versions" / "1.1.0").exists()
    (tmp_path / "versions" / ".staging-1.2.0").mkdir()
    assert not list((Installer(tmp_path).root / "versions").glob(".staging-*"))  # a leftover from a crash is cleaned at the next start
    assert r2.version == "1.1.0"


@pytest.mark.parametrize("name", ["../escape.txt", "/abs/path.txt", "a/../../escape.txt"])
def test_an_artefact_that_writes_outside_its_own_folder_is_refused(tmp_path, name):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(zipfile.ZipInfo(name), b"x")
    art = buffer.getvalue()
    inst = Installer(tmp_path / "app")
    with pytest.raises(UpdateError) as e:
        inst.install(release("1.0.0", art), art, lambda p: True)
    assert e.value.code == "unsafe_artefact" and not (tmp_path / "escape.txt").exists() and inst.current_version() is None


def test_a_symbolic_link_inside_an_artefact_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        z.writestr(info, "/etc/passwd")
    art = buffer.getvalue()
    with pytest.raises(UpdateError) as e:
        Installer(tmp_path).install(release("1.0.0", art), art, lambda p: True)
    assert e.value.code == "unsafe_artefact"


def test_an_explicit_rollback_returns_to_the_previous_version_and_can_itself_be_undone(tmp_path):
    inst = Installer(tmp_path)
    with pytest.raises(UpdateError) as e:
        inst.rollback()
    assert e.value.code == "nothing_to_roll_back_to"
    for v in ("1.0.0", "1.1.0"):
        r, a = good(v, v.encode())
        inst.install(r, a, lambda p: True)
    assert inst.rollback() == "1.0.0" and inst.current_version() == "1.0.0"
    assert inst.rollback() == "1.1.0"  # and forward again
    assert Path(tmp_path / "current").is_symlink()
