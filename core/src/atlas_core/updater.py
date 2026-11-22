"""Authenticated update, atomic install and rollback of the app bundle (Stage 7). The owner's DATA is never touched by any of this.

* **Signed.** A release is a manifest (version, size, SHA-256 of the artefact) signed with an Ed25519 key whose PUBLIC half is installed with the app. An unsigned, wrongly signed or altered manifest, or an
  artefact that does not match its hash, is refused before anything is unpacked.
* **Never backwards by accident.** An update must be strictly newer than what is installed. Going back is a separate, explicit `rollback`, and only to a version that is still on disk.
* **Atomic.** The new version is unpacked into its own folder (no absolute paths, no `..`, no links), then a single `current` link is switched. A crash at any point leaves either the old version or the new one
  as `current`, never a mix. The previous version stays on disk, and a failed health check after the switch rolls back by itself.
* **Data compatibility.** The Core's stores are additive and versioned and refuse a newer schema than they understand, so rolling the app back never silently corrupts the data folder; this module does not
  open, move or migrate that folder.

The update CHANNEL (where the manifest and artefact are fetched from, and the one-click UI) is a separate seam: this module is given bytes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_VERSION = re.compile(r"(\d{1,4})\.(\d{1,4})\.(\d{1,6})\Z")
MAX_ARTEFACT_BYTES = 2 * 1024**3
MAX_FILES = 200_000
FILE_TYPE_MASK, SYMLINK_TYPE = 0o170000, 0o120000  # the Unix file-type bits kept in a zip member's attributes


class UpdateError(Exception):
    """An update step was refused. Carries a code and nothing else."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_version(text: str) -> tuple[int, int, int]:
    match = _VERSION.match(text)
    if match is None:
        raise UpdateError("bad_version")
    return int(match[1]), int(match[2]), int(match[3])


@dataclass(frozen=True)
class Release:
    version: str
    sha256: str
    size: int


def verify_release(manifest: bytes, signature: bytes, public_key: Ed25519PublicKey) -> Release:
    try:
        public_key.verify(signature, manifest)
    except InvalidSignature:
        raise UpdateError("bad_signature") from None
    try:
        doc = json.loads(manifest)
        release = Release(str(doc["version"]), str(doc["sha256"]), int(doc["size"]))
    except (ValueError, KeyError, TypeError):
        raise UpdateError("bad_manifest") from None
    parse_version(release.version)
    if not re.fullmatch(r"[0-9a-f]{64}", release.sha256) or not 0 < release.size <= MAX_ARTEFACT_BYTES:
        raise UpdateError("bad_manifest")
    return release


def _safe_extract(artefact: bytes, destination: Path) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(artefact))
    except zipfile.BadZipFile:
        raise UpdateError("bad_artefact") from None
    members = archive.infolist()
    if len(members) > MAX_FILES:
        raise UpdateError("bad_artefact")
    root = destination.resolve()
    for member in members:
        target = (root / member.filename).resolve()
        mode = member.external_attr >> 16
        if not target.is_relative_to(root) or member.filename.startswith("/") or (mode & FILE_TYPE_MASK) == SYMLINK_TYPE:
            raise UpdateError("unsafe_artefact")  # an absolute path, a `..`, or a symbolic link
    archive.extractall(root)


class Installer:
    """`root/versions/<v>/`, `root/current` (a link to the running version) and `root/previous` (a link to the one before)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "versions").mkdir(parents=True, exist_ok=True)
        for leftover in (root / "versions").glob(".staging-*"):
            shutil.rmtree(leftover, ignore_errors=True)  # a crash left half an unpack: it was never `current`

    def _link(self, name: str) -> Path:
        return self.root / name

    def current_version(self) -> str | None:
        link = self._link("current")
        return os.path.basename(os.readlink(link)) if link.is_symlink() else None

    def _point(self, name: str, version: str) -> None:
        temporary = self.root / f".{name}.new"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(Path("versions") / version)
        os.replace(temporary, self._link(name))  # one atomic rename: a reader sees the old target or the new one

    def install(self, release: Release, artefact: bytes, healthy: Callable[[Path], bool]) -> str:
        """Verify, unpack, switch, check health, and roll back by itself if the new version is not healthy. Returns the version that is current afterwards."""
        if len(artefact) != release.size or hashlib.sha256(artefact).hexdigest() != release.sha256:
            raise UpdateError("artefact_does_not_match_manifest")
        installed = self.current_version()
        if installed is not None and parse_version(release.version) <= parse_version(installed):
            raise UpdateError("not_newer")  # never backwards by accident
        final = self.root / "versions" / release.version
        if final.exists():
            raise UpdateError("version_already_on_disk")
        staging = self.root / "versions" / f".staging-{release.version}"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        try:
            _safe_extract(artefact, staging)
            os.rename(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if installed is not None:
            self._point("previous", installed)
        self._point("current", release.version)
        if healthy(final):
            return release.version
        if installed is not None:
            self._point("current", installed)  # the new version failed its health check: back to the one that worked
            raise UpdateError("unhealthy_rolled_back")
        raise UpdateError("unhealthy_first_install")

    def rollback(self) -> str:
        """Explicitly return to the previous version, if it is still on disk."""
        link = self._link("previous")
        if not link.is_symlink() or not (self.root / "versions" / os.path.basename(os.readlink(link))).is_dir():
            raise UpdateError("nothing_to_roll_back_to")
        target, running = os.path.basename(os.readlink(link)), self.current_version()
        self._point("current", target)
        if running is not None:
            self._point("previous", running)  # so the rollback can itself be undone
        return target
