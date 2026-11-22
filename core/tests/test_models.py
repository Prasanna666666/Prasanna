"""WP3.4a: the signed model manifest and the import/load verification (INTELLIGENCE_AND_PERFORMANCE.md §5.4). Synthetic files only; no model is ever loaded."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atlas_core.models import MANIFEST_VERSION, Manifest, ModelRejected, ModelStore, canonical, parse_entry

KEY = Ed25519PrivateKey.generate()
RECORD_KEY = b"k" * 32


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def entry_dict(model_id: str = "primary-1", files: dict[str, bytes] | None = None, **over) -> dict:
    files = files if files is not None else {"w.safetensors": b"weights", "config.json": b"{}"}
    raw = {
        "model_id": model_id, "role": "primary", "runtime": "stub", "capabilities": ["text", "image"], "developer": "Example Lab", "developer_jurisdiction": "US",
        "upstream_id": "example/model", "upstream_revision": "r1", "licence_name": "Apache-2.0", "licence_sha256": sha(b"lic"),
        "lineage_disclosure": "Trained from scratch; no distillation disclosed.", "quantisation": "4-bit", "conversion_chain": "tool 1.0 from r1",
        "context_tokens": 32768, "resident_bytes": 1000, "files": [{"path": p, "sha256": sha(b), "size": len(b)} for p, b in files.items()],
    }  # fmt: skip
    raw.update(over)
    return raw


def signed(entries: list[dict], key: Ed25519PrivateKey = KEY) -> Manifest:
    doc = canonical({"manifest_version": MANIFEST_VERSION, "entries": entries})
    return Manifest.from_signed(doc, key.sign(doc), key.public_key())


def store(tmp_path: Path, files: dict[str, bytes] | None = None, **over) -> tuple[ModelStore, Path]:
    files = files if files is not None else {"w.safetensors": b"weights", "config.json": b"{}"}
    d = tmp_path / "primary-1"
    d.mkdir()
    for p, b in files.items():
        (d / p).write_bytes(b)
    return ModelStore(tmp_path, signed([entry_dict(files=files, **over)]), RECORD_KEY), d


def reason(fn) -> str:
    with pytest.raises(ModelRejected) as e:
        fn()
    return e.value.reason


def test_a_signed_manifest_loads_and_an_unknown_model_is_refused():
    m = signed([entry_dict()])
    assert m.get("primary-1").role == "primary"
    assert reason(lambda: m.get("other")) == "not_in_manifest"


def test_a_wrong_signature_or_altered_document_is_refused():
    doc = canonical({"manifest_version": 1, "entries": [entry_dict()]})
    other = Ed25519PrivateKey.generate()
    assert reason(lambda: Manifest.from_signed(doc, other.sign(doc), KEY.public_key())) == "bad_signature"
    assert reason(lambda: Manifest.from_signed(doc + b" ", KEY.sign(doc), KEY.public_key())) == "bad_signature"


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"developer_jurisdiction": "cn"}, "lineage_excluded"), ({"lineage_disclosure": " "}, "bad_manifest"), ({"role": "coder"}, "bad_manifest"),
        ({"capabilities": ["image"]}, "bad_manifest"), ({"model_id": "../x"}, "bad_manifest"), ({"context_tokens": 0}, "bad_manifest"),
        ({"licence_sha256": "zz"}, "bad_manifest"), ({"runtime": "torch"}, "bad_manifest"),
    ],
)  # fmt: skip
def test_entries_are_strict(over, code):
    assert reason(lambda: signed([entry_dict(**over)])) == code


@pytest.mark.parametrize("path", ["model.bin", "m.pt", "m.pkl", "run.py", "m.zip", "w.safetensors.py"])
def test_pickle_and_code_files_are_refused(path):
    raw = entry_dict(files={"w.safetensors": b"x"})
    raw["files"].append({"path": path, "sha256": sha(b"x"), "size": 1})
    assert reason(lambda: parse_entry(raw)) == "bad_format"


def test_an_entry_needs_a_weight_file_and_safe_paths():
    assert reason(lambda: parse_entry(entry_dict(files={"config.json": b"{}"}))) == "bad_format"
    for bad in ("/abs/w.safetensors", "../w.safetensors"):
        raw = entry_dict()
        raw["files"][0]["path"] = bad
        assert reason(lambda raw=raw: parse_entry(raw)) == "bad_manifest"


def test_an_extra_or_missing_field_or_duplicate_id_is_refused():
    raw = entry_dict()
    raw["extra"] = 1
    assert reason(lambda: parse_entry(raw)) == "bad_manifest"
    assert reason(lambda: signed([entry_dict(), entry_dict()])) == "bad_manifest"


def test_import_then_load_computes_no_new_digest_and_files_become_read_only(tmp_path):
    s, d = store(tmp_path)
    s.import_model("primary-1")
    assert s.full_hashes == 2
    assert not os.access(d / "w.safetensors", os.W_OK) or os.geteuid() == 0
    assert (d / "w.safetensors").stat().st_mode & 0o222 == 0
    v = s.verify_for_load("primary-1")
    assert s.full_hashes == 2 and s.still_verified(v)


def test_load_without_import_is_refused(tmp_path):
    s, _ = store(tmp_path)
    assert reason(lambda: s.verify_for_load("primary-1")) == "not_imported"


def test_import_refuses_wrong_bytes_and_missing_files(tmp_path):
    s, d = store(tmp_path)
    (d / "w.safetensors").write_bytes(b"WEIGHTS")  # same size, different bytes
    assert reason(lambda: s.import_model("primary-1")) == "digest_mismatch"
    (d / "w.safetensors").unlink()
    assert reason(lambda: s.import_model("primary-1")) == "digest_mismatch"


def test_a_symlinked_weight_file_is_refused(tmp_path):
    s, d = store(tmp_path)
    real = tmp_path / "elsewhere"
    real.write_bytes(b"weights")
    (d / "w.safetensors").unlink()
    (d / "w.safetensors").symlink_to(real)
    assert reason(lambda: s.import_model("primary-1")) == "digest_mismatch"


def test_a_changed_file_after_import_is_refused_even_if_the_size_matches(tmp_path):
    s, d = store(tmp_path)
    s.import_model("primary-1")
    p = d / "w.safetensors"
    p.chmod(0o644)
    p.write_bytes(b"WEIGHTS")
    p.chmod(0o444)
    assert reason(lambda: s.verify_for_load("primary-1")) == "digest_mismatch"
    assert s.full_hashes == 3  # the identity changed, so the whole file was hashed again


def test_a_writable_file_is_rehashed_and_refused_even_when_the_bytes_are_right(tmp_path):
    s, d = store(tmp_path)
    s.import_model("primary-1")
    (d / "w.safetensors").chmod(0o644)
    assert reason(lambda: s.verify_for_load("primary-1")) == "not_read_only"


def test_a_tampered_import_record_is_refused(tmp_path):
    s, _ = store(tmp_path)
    s.import_model("primary-1")
    rec = tmp_path / "primary-1.import.json"
    data = json.loads(rec.read_text())
    data["files"][0][1][0] += 1
    rec.write_text(json.dumps(data))
    assert reason(lambda: s.verify_for_load("primary-1")) == "record_tampered"
    rec.write_text("not json")
    assert reason(lambda: s.verify_for_load("primary-1")) == "not_imported"
    rec.write_text("[]")
    assert reason(lambda: s.verify_for_load("primary-1")) == "record_tampered"


def test_a_record_made_under_another_key_is_refused(tmp_path):
    s, _d = store(tmp_path)
    s.import_model("primary-1")
    other = ModelStore(tmp_path, s._manifest, b"z" * 32)
    assert reason(lambda: other.verify_for_load("primary-1")) == "record_tampered"


def test_a_swap_after_load_is_detected(tmp_path):
    s, d = store(tmp_path)
    s.import_model("primary-1")
    v = s.verify_for_load("primary-1")
    p = d / "w.safetensors"
    p.chmod(0o644)
    p.write_bytes(b"swapped")
    assert not s.still_verified(v)
    p.unlink()
    assert not s.still_verified(v)


def test_a_short_record_key_is_refused(tmp_path):
    with pytest.raises(ValueError, match="short"):
        ModelStore(tmp_path, signed([entry_dict()]), b"x")
