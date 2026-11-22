"""The approved-model manifest and the supply-chain checks that stand between a file on disk and a model that may be loaded.

Recorded decision (INTELLIGENCE_AND_PERFORMANCE.md §5.4): every model has a manifest entry (developer and accountable release organisation, upstream id and revision, disclosed
lineage, licence, quantisation and conversion chain, runtime, capabilities, the SHA-256 of every file). The manifest is SIGNED; a model that is not in it never loads; only
safetensors or GGUF weights are accepted (never pickle, never code that a model ships); the full digest is verified when the model is IMPORTED and again whenever the file's
identity changes; at load the file must be the exact, read-only file that was verified. Anything that cannot be shown to hold fails closed.

Nothing here reads the model itself or opens a network connection: it only hashes and compares files.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MANIFEST_VERSION = 1
ROLES = ("primary", "text_fallback", "multimodal_fallback", "deep")
RUNTIMES = ("mlx", "stub")
CAPABILITIES = ("text", "image", "audio")
ALLOWED_SUFFIXES = (
    ".safetensors",
    ".gguf",
    ".json",
    ".txt",
    ".model",
    ".jinja",
)  # weights, configuration and tokenizer data: nothing executable, nothing pickled
WEIGHT_SUFFIXES = (".safetensors", ".gguf")
EXCLUDED_JURISDICTIONS = frozenset({"CN"})  # the owner's lineage rule: developer and accountable release organisation outside the PRC (ISO 3166 country code)
_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_CHUNK = 8 * 1024 * 1024


class ModelRejected(Exception):
    """A model that may not be loaded. `reason` is a code (never a path or content): not_in_manifest, bad_signature, bad_manifest, bad_format, digest_mismatch, not_imported,
    record_tampered, identity_changed, not_read_only, lineage_excluded."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class FileDigest:
    path: str  # relative to the model's folder, no '..', no absolute path
    sha256: str
    size: int


@dataclass(frozen=True)
class ManifestEntry:
    model_id: str
    role: str
    runtime: str
    capabilities: tuple[str, ...]
    developer: str
    developer_jurisdiction: str  # ISO 3166 country code of the developer and accountable release organisation
    upstream_id: str
    upstream_revision: str
    licence_name: str
    licence_sha256: str  # digest of the licence text archived with the model
    lineage_disclosure: str  # what the card and technical report disclose about base, derivative and distillation (a short statement, never empty)
    quantisation: str
    conversion_chain: str  # who converted the weights, with which tool and version, from which upstream revision
    context_tokens: int  # the context the entry is approved for (the default is 32K)
    resident_bytes: int  # the planning figure for the resident weights (an estimate until measured)
    files: tuple[FileDigest, ...]


def _file(raw: Any) -> FileDigest:
    if not isinstance(raw, dict) or set(raw) != {"path", "sha256", "size"}:
        raise ModelRejected("bad_manifest")
    path, digest, size = raw["path"], raw["sha256"], raw["size"]
    if not (isinstance(path, str) and isinstance(digest, str) and _HEX.match(digest) and isinstance(size, int) and not isinstance(size, bool) and size >= 0):
        raise ModelRejected("bad_manifest")
    parts = Path(path).parts
    if not parts or Path(path).is_absolute() or ".." in parts or "\x00" in path:
        raise ModelRejected("bad_manifest")
    if not path.lower().endswith(ALLOWED_SUFFIXES):
        raise ModelRejected("bad_format")  # pickle, code, archives: never
    return FileDigest(path, digest, size)


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 500:  # noqa: PLR2004
        raise ModelRejected("bad_manifest")
    return value


def parse_entry(raw: Any) -> ManifestEntry:
    """A strict entry: every field present and typed, the lineage fields non-empty, the developer outside the excluded jurisdictions, at least one weight file."""
    fields = set(ManifestEntry.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) != fields:
        raise ModelRejected("bad_manifest")
    model_id = raw["model_id"]
    capabilities = raw["capabilities"]
    ok = (
        isinstance(model_id, str)
        and bool(_ID.match(model_id))
        and raw["role"] in ROLES
        and raw["runtime"] in RUNTIMES
        and isinstance(capabilities, list)
        and bool(capabilities)
        and set(capabilities) <= set(CAPABILITIES)
        and "text" in capabilities
        and isinstance(raw["files"], list)
        and bool(raw["files"])
        and all(isinstance(raw[k], int) and not isinstance(raw[k], bool) and raw[k] > 0 for k in ("context_tokens", "resident_bytes"))
        and isinstance(raw["licence_sha256"], str)
        and bool(_HEX.match(raw["licence_sha256"]))
    )
    if not ok:
        raise ModelRejected("bad_manifest")
    jurisdiction = _text(raw, "developer_jurisdiction").upper()
    if jurisdiction in EXCLUDED_JURISDICTIONS:
        raise ModelRejected("lineage_excluded")
    files = tuple(_file(f) for f in raw["files"])
    if not any(f.path.lower().endswith(WEIGHT_SUFFIXES) for f in files):
        raise ModelRejected("bad_format")
    texts = {
        k: _text(raw, k) for k in ("developer", "upstream_id", "upstream_revision", "licence_name", "lineage_disclosure", "quantisation", "conversion_chain")
    }
    return ManifestEntry(
        model_id, raw["role"], raw["runtime"], tuple(capabilities), texts["developer"], jurisdiction, texts["upstream_id"], texts["upstream_revision"],
        texts["licence_name"], raw["licence_sha256"], texts["lineage_disclosure"], texts["quantisation"], texts["conversion_chain"],
        raw["context_tokens"], raw["resident_bytes"], files,
    )  # fmt: skip


def canonical(manifest: dict[str, Any]) -> bytes:
    return json.dumps({"manifest_version": manifest["manifest_version"], "entries": manifest["entries"]}, sort_keys=True, separators=(",", ":")).encode()


class Manifest:
    """The approved models. Built only from a document whose signature verifies under the installed public key; nothing else can add an entry."""

    def __init__(self, entries: Iterable[ManifestEntry]) -> None:
        self._entries = {e.model_id: e for e in entries}

    @classmethod
    def from_signed(cls, document: bytes, signature: bytes, public_key: Ed25519PublicKey) -> Manifest:
        try:
            public_key.verify(signature, document)
        except InvalidSignature:
            raise ModelRejected("bad_signature") from None
        try:
            manifest = json.loads(document)
        except ValueError:
            raise ModelRejected("bad_manifest") from None
        if not (isinstance(manifest, dict) and manifest.get("manifest_version") == MANIFEST_VERSION and isinstance(manifest.get("entries"), list)):
            raise ModelRejected("bad_manifest")
        entries = [parse_entry(e) for e in manifest["entries"]]
        if len({e.model_id for e in entries}) != len(entries):
            raise ModelRejected("bad_manifest")
        return cls(entries)

    def get(self, model_id: str) -> ManifestEntry:
        entry = self._entries.get(model_id)
        if entry is None:
            raise ModelRejected("not_in_manifest")
        return entry

    def entries(self) -> list[ManifestEntry]:
        return sorted(self._entries.values(), key=lambda e: e.model_id)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(path: Path) -> list[int]:
    st = path.stat()
    return [st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev]


def _read_only(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) & 0o222 == 0  # mode bits, not os.access (a privileged user can always write)


@dataclass(frozen=True)
class VerifiedModel:
    """The exact files that were verified, for the runtime to load. `root` is the folder; nothing outside `files` belongs to the model."""

    entry: ManifestEntry
    root: Path
    identities: tuple[tuple[str, tuple[int, ...]], ...]


class ModelStore:
    """Imports models into a read-only store and decides, at load, whether the bytes on disk are still the bytes that were verified.

    `import_model` hashes every file (full digest), compares it to the signed manifest, makes the files read-only and writes an HMAC-protected record of each file's identity.
    `verify_for_load` then checks the record (so a tampered record is refused), that each file's identity (size, modification time, inode, device) and read-only state are
    unchanged, and otherwise re-hashes the whole file instead of trusting metadata: a changed identity is never accepted without a fresh full digest.
    """

    def __init__(self, root: Path, manifest: Manifest, record_key: bytes) -> None:
        if len(record_key) < 16:  # noqa: PLR2004
            raise ValueError("record key too short")
        self.root, self._manifest, self._key = root, manifest, record_key
        self.full_hashes = 0  # tests: how many full digests were computed (a load of an unchanged, read-only model computes none)

    def entry(self, model_id: str) -> ManifestEntry:
        """The approved entry (raises ModelRejected `not_in_manifest`)."""
        return self._manifest.get(model_id)

    def _dir(self, entry: ManifestEntry) -> Path:
        return self.root / entry.model_id

    def _record_path(self, entry: ManifestEntry) -> Path:
        return self.root / f"{entry.model_id}.import.json"

    def _mac(self, entry: ManifestEntry, identities: list[list[Any]]) -> str:
        body = json.dumps({"model_id": entry.model_id, "files": identities}, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()

    def _check_file(self, entry: ManifestEntry, item: FileDigest) -> Path:
        path = self._dir(entry) / item.path
        if not path.is_file() or path.is_symlink() or path.stat().st_size != item.size:
            raise ModelRejected("digest_mismatch")
        return path

    def import_model(self, model_id: str) -> VerifiedModel:
        """Full digest of every file against the signed manifest; on success the files become read-only and the import is recorded."""
        entry = self._manifest.get(model_id)
        identities: list[list[Any]] = []
        for item in entry.files:
            path = self._check_file(entry, item)
            self.full_hashes += 1
            if sha256_file(path) != item.sha256:
                raise ModelRejected("digest_mismatch")
            path.chmod(0o444)
            identities.append([item.path, _identity(path)])
        record = {"model_id": entry.model_id, "files": identities, "mac": self._mac(entry, identities)}
        self._record_path(entry).write_text(json.dumps(record))
        return VerifiedModel(entry, self._dir(entry), tuple((p, tuple(i)) for p, i in identities))

    def verify_for_load(self, model_id: str) -> VerifiedModel:
        entry = self._manifest.get(model_id)
        try:
            record = json.loads(self._record_path(entry).read_text())
        except (OSError, ValueError):
            raise ModelRejected("not_imported") from None
        if not (isinstance(record, dict) and record.get("model_id") == entry.model_id and isinstance(record.get("files"), list)):
            raise ModelRejected("record_tampered")
        recorded = record["files"]
        if not hmac.compare_digest(str(record.get("mac")), self._mac(entry, recorded)):
            raise ModelRejected("record_tampered")
        known = {p: tuple(i) for p, i in recorded}
        identities: list[tuple[str, tuple[int, ...]]] = []
        for item in entry.files:
            path = self._check_file(entry, item)
            if known.get(item.path) != tuple(_identity(path)) or not _read_only(path):
                self.full_hashes += 1  # the identity changed or the file became writable: metadata is no proof, so hash the whole file again
                if sha256_file(path) != item.sha256:
                    raise ModelRejected("digest_mismatch")
                if not _read_only(path):
                    raise ModelRejected("not_read_only")  # correct bytes, but not protected from being replaced during use
            identities.append((item.path, tuple(_identity(path))))
        return VerifiedModel(entry, self._dir(entry), tuple(identities))

    def still_verified(self, verified: VerifiedModel) -> bool:
        """After a load: are the files still exactly the verified ones? (A swap during the load window means the model must be unloaded and rejected.)"""
        for path, identity in verified.identities:
            file = verified.root / path
            if not file.is_file() or tuple(_identity(file)) != identity or not _read_only(file):
                return False
        return True


__all__ = [
    "ALLOWED_SUFFIXES", "CAPABILITIES", "EXCLUDED_JURISDICTIONS", "ROLES", "RUNTIMES", "FileDigest", "Manifest", "ManifestEntry", "ModelRejected", "ModelStore",
    "VerifiedModel", "canonical", "parse_entry", "sha256_file",
]  # fmt: skip
