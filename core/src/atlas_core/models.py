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
import os
import re
import shutil
import stat
import tempfile
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


_NOFOLLOW = os.O_NOFOLLOW
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | _NOFOLLOW | os.O_NONBLOCK


def _identity_of(st: os.stat_result) -> list[int]:
    return [st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev]


def _walk(root_fd: int, parts: tuple[str, ...]) -> int:
    """The directory descriptor of `parts` below `root_fd`, opened one component at a time with O_NOFOLLOW: no component (a parent included) may be a link."""
    current = os.dup(root_fd)
    try:
        for part in parts:
            nxt = os.open(part, _DIR_FLAGS, dir_fd=current)
            os.close(current)
            current = nxt
        return current
    except BaseException:
        os.close(current)
        raise


def _open_confined(root_fd: int, rel: str) -> int:
    """A read-only descriptor of the regular file `rel` below `root_fd`, no link followed at ANY component. ModelRejected `digest_mismatch` otherwise (a content-free code)."""
    parts = Path(rel).parts
    try:
        parent = _walk(root_fd, parts[:-1])
        try:
            fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
        finally:
            os.close(parent)
    except OSError:
        raise ModelRejected("digest_mismatch") from None
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ModelRejected("digest_mismatch")
    return fd


def _hash_fd(fd: int) -> str:
    """The digest of what the descriptor holds, read from the start (the very bytes the descriptor points at, whatever happens to the name)."""
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while block := os.read(fd, _CHUNK):
        digest.update(block)
    return digest.hexdigest()


def _read_only_mode(st: os.stat_result) -> bool:
    return stat.S_IMODE(st.st_mode) & 0o222 == 0  # mode bits, not os.access (a privileged user can always write)


@dataclass(frozen=True)
class VerifiedModel:
    """The exact files that were verified, for the runtime to load. `root` is the folder the runtime may read: for a staged model it holds ONLY the manifest's files, as links to
    (or hash-checked copies of) the verified bytes, so nothing unmanifested can be consumed. `identities` are those files' size, modification time, inode and device."""

    entry: ManifestEntry
    root: Path
    identities: tuple[tuple[str, tuple[int, ...]], ...]
    staged: bool = False


class ModelStore:
    """Imports models into a read-only store and decides, at load, whether the bytes on disk are still the bytes that were verified.

    Every path is opened one component at a time without following a link (a symlinked parent directory cannot redirect a manifest path out of the model folder) and every digest is
    computed from the open descriptor, so what is hashed is exactly what that descriptor holds. `import_model` hashes each file against the signed manifest, makes it read-only and
    records an HMAC-protected identity. `verify_for_load` re-checks the record and identities and re-hashes any file whose identity changed. `stage` then builds the directory the
    runtime loads from: only manifest files, hard-linked (same inode, so a later rename or replacement of the original name cannot change what was verified) and confirmed to be the
    inode that was hashed, or, where links are impossible, copied while hashing. `still_verified` detects an in-place change after loading. Threat model: other processes and
    accidents; a process running as the same user that deliberately rewrites a read-only file and its timestamps is not defended against here.
    """

    def __init__(self, root: Path, manifest: Manifest, record_key: bytes) -> None:
        if len(record_key) < 16:  # noqa: PLR2004
            raise ValueError("record key too short")
        self.root, self._manifest, self._key = root, manifest, record_key
        self.full_hashes = 0  # tests: how many full digests were computed (a load of an unchanged, read-only model computes none)
        shutil.rmtree(root / ".load", ignore_errors=True)  # staging left behind by a crash

    def entry(self, model_id: str) -> ManifestEntry:
        """The approved entry (raises ModelRejected `not_in_manifest`)."""
        return self._manifest.get(model_id)

    def _record_path(self, entry: ManifestEntry) -> Path:
        return self.root / f"{entry.model_id}.import.json"

    def _mac(self, entry: ManifestEntry, identities: list[list[Any]]) -> str:
        body = json.dumps({"model_id": entry.model_id, "files": identities}, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()

    def _model_fd(self, entry: ManifestEntry) -> int:
        """The model's own folder, opened below the (trusted) store root without following a link."""
        try:
            top = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            raise ModelRejected("digest_mismatch") from None
        try:
            return _walk(top, (entry.model_id,))
        except OSError:
            raise ModelRejected("digest_mismatch") from None
        finally:
            os.close(top)

    def import_model(self, model_id: str) -> VerifiedModel:
        """Full digest of every file against the signed manifest; on success the files become read-only and the import is recorded."""
        entry = self._manifest.get(model_id)
        identities: list[list[Any]] = []
        model = self._model_fd(entry)
        try:
            for item in entry.files:
                fd = _open_confined(model, item.path)
                try:
                    self.full_hashes += 1
                    if os.fstat(fd).st_size != item.size or _hash_fd(fd) != item.sha256:
                        raise ModelRejected("digest_mismatch")
                    os.fchmod(fd, 0o444)
                    identities.append([item.path, _identity_of(os.fstat(fd))])
                finally:
                    os.close(fd)
        finally:
            os.close(model)
        record = {"model_id": entry.model_id, "files": identities, "mac": self._mac(entry, identities)}
        temporary = self._record_path(entry).with_suffix(".tmp")
        temporary.write_text(json.dumps(record))
        temporary.replace(self._record_path(entry))
        return VerifiedModel(entry, self.root / entry.model_id, tuple((p, tuple(i)) for p, i in identities))

    def _recorded(self, entry: ManifestEntry) -> dict[str, tuple[int, ...]]:
        try:
            record = json.loads(self._record_path(entry).read_text())
        except (OSError, ValueError):
            raise ModelRejected("not_imported") from None
        if not (isinstance(record, dict) and record.get("model_id") == entry.model_id and isinstance(record.get("files"), list)):
            raise ModelRejected("record_tampered")
        recorded = record["files"]
        if not hmac.compare_digest(str(record.get("mac")), self._mac(entry, recorded)):
            raise ModelRejected("record_tampered")
        return {p: tuple(i) for p, i in recorded}

    def verify_for_load(self, model_id: str) -> VerifiedModel:
        """Check the model in the store against the signed manifest and the import record (no staging yet)."""
        entry = self._manifest.get(model_id)
        known = self._recorded(entry)
        identities: list[tuple[str, tuple[int, ...]]] = []
        model = self._model_fd(entry)
        try:
            for item in entry.files:
                fd = _open_confined(model, item.path)
                try:
                    st = os.fstat(fd)
                    if st.st_size != item.size:
                        raise ModelRejected("digest_mismatch")
                    if known.get(item.path) != tuple(_identity_of(st)) or not _read_only_mode(st):
                        self.full_hashes += 1  # the identity changed or the file became writable: metadata is no proof, so hash the whole file again
                        if _hash_fd(fd) != item.sha256:
                            raise ModelRejected("digest_mismatch")
                        if not _read_only_mode(st):
                            raise ModelRejected("not_read_only")  # correct bytes, but not protected from being replaced during use
                    identities.append((item.path, tuple(_identity_of(st))))
                finally:
                    os.close(fd)
        finally:
            os.close(model)
        return VerifiedModel(entry, self.root / entry.model_id, tuple(identities))

    def stage(self, verified: VerifiedModel) -> VerifiedModel:
        """The directory the runtime loads from: only the manifest's files, each the verified inode (hard link) or a hash-checked copy. The caller must `release` it."""
        entry = verified.entry
        stage_root = self.root / ".load"
        stage_root.mkdir(mode=0o700, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix=f"{entry.model_id}-", dir=stage_root))
        target.chmod(0o700)
        wanted = dict(verified.identities)
        source, out = self._model_fd(entry), []
        try:
            for item in entry.files:
                destination = target / item.path
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                parts = Path(item.path).parts
                parent = _walk(source, parts[:-1])
                try:
                    try:
                        os.link(parts[-1], destination, src_dir_fd=parent, follow_symlinks=False)
                    except OSError:
                        self._copy(parent, parts[-1], destination, item)  # a different filesystem, or links not allowed: a copy that is hashed as it is written
                finally:
                    os.close(parent)
                out.append((item.path, self._check_staged(destination, item, wanted.get(item.path))))
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        finally:
            os.close(source)
        return VerifiedModel(entry, target, tuple(out), staged=True)

    def _copy(self, parent: int, name: str, destination: Path, item: FileDigest) -> None:
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=parent)
        except OSError:
            raise ModelRejected("digest_mismatch") from None
        digest = hashlib.sha256()
        try:
            self.full_hashes += 1
            with destination.open("wb") as out:
                while block := os.read(fd, _CHUNK):
                    digest.update(block)
                    out.write(block)
        finally:
            os.close(fd)
        if digest.hexdigest() != item.sha256:
            raise ModelRejected("digest_mismatch")
        destination.chmod(0o444)

    def _check_staged(self, path: Path, item: FileDigest, verified_identity: tuple[int, ...] | None) -> tuple[int, ...]:
        """The staged file must be a regular, read-only file of the right size; a link must be the very inode that was verified (a name swapped between verification and linking is
        caught here); anything else (a copy) was hashed while it was written."""
        try:
            fd = os.open(path, _FILE_FLAGS)
        except OSError:
            raise ModelRejected("digest_mismatch") from None
        try:
            st = os.fstat(fd)
            linked = st.st_nlink > 1
            if not stat.S_ISREG(st.st_mode) or st.st_size != item.size or not _read_only_mode(st):
                raise ModelRejected("digest_mismatch")
            identity = tuple(_identity_of(st))
            if linked and identity != verified_identity:
                raise ModelRejected("identity_changed")
            return identity
        finally:
            os.close(fd)

    def release(self, verified: VerifiedModel) -> None:
        """Remove a staged directory (the links go; the verified originals stay)."""
        if verified.staged and verified.root.parent == self.root / ".load":
            shutil.rmtree(verified.root, ignore_errors=True)

    def still_verified(self, verified: VerifiedModel) -> bool:
        """After a load: are the files still exactly the verified ones? An in-place change (size, modification time, inode) or a writable file means the model must be unloaded and
        rejected. A staged directory is checked without following links."""
        try:
            top = os.open(verified.root, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            return False
        try:
            for path, identity in verified.identities:
                try:
                    fd = _open_confined(top, path)
                except ModelRejected:
                    return False
                try:
                    st = os.fstat(fd)
                    if tuple(_identity_of(st)) != identity or not _read_only_mode(st):
                        return False
                finally:
                    os.close(fd)
            return True
        finally:
            os.close(top)


__all__ = [
    "ALLOWED_SUFFIXES", "CAPABILITIES", "EXCLUDED_JURISDICTIONS", "ROLES", "RUNTIMES", "FileDigest", "Manifest", "ManifestEntry", "ModelRejected", "ModelStore",
    "VerifiedModel", "canonical", "parse_entry", "sha256_file",
]  # fmt: skip
