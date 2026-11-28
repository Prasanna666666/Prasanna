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

from .errors import UpdateError

_VERSION = re.compile(r"(\d{1,4})\.(\d{1,4})\.(\d{1,6})\Z")
MAX_ARTEFACT_BYTES = 2 * 1024**3
MAX_FILES = 200_000
MAX_EXPANDED_BYTES = 8 * 1024**3  # the whole unpacked bundle; a signed update still may not fill the volume
MAX_MEMBER_BYTES = 4 * 1024**3
MAX_RATIO = 200  # uncompressed : compressed, for any member over 1 MiB
FILE_TYPE_MASK, SYMLINK_TYPE = 0o170000, 0o120000  # the Unix file-type bits kept in a zip member's attributes


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
    _check_sizes(members)
    written = 0
    for member in members:  # member by member, counting the bytes actually written, so deceptive size metadata cannot get past the ceiling
        if member.is_dir():
            (root / member.filename).mkdir(parents=True, exist_ok=True)
            continue
        out = root / member.filename
        out.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, out.open("wb") as sink:
            while block := source.read(1 << 20):
                written += len(block)
                if written > MAX_EXPANDED_BYTES:
                    raise UpdateError("unsafe_artefact")
                sink.write(block)
        mode = (member.external_attr >> 16) & 0o777
        if mode:
            out.chmod(mode)


def _check_sizes(members: list[zipfile.ZipInfo]) -> None:
    """Refuse before extracting: a negative or oversized declared size, an aggregate over the ceiling, or an extreme compression ratio (a ZIP bomb). A signature proves who published an update, not that it is safe to expand."""
    total = 0
    for member in members:
        if member.file_size < 0 or member.file_size > MAX_MEMBER_BYTES:
            raise UpdateError("unsafe_artefact")
        if member.compress_size and member.file_size / member.compress_size > MAX_RATIO and member.file_size > (1 << 20):
            raise UpdateError("unsafe_artefact")
        total += member.file_size
    if total > MAX_EXPANDED_BYTES:
        raise UpdateError("unsafe_artefact")


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
        try:
            ok = bool(healthy(final))
        except Exception:  # noqa: BLE001 - a health check that raises is a failed health check, never a reason to stay on the new version
            ok = False
        if ok:
            return release.version
        if installed is not None:
            self._point("current", installed)  # the new version failed its health check: back to the one that worked
            raise UpdateError("unhealthy_rolled_back")
        self._link("current").unlink(missing_ok=True)  # first install: nothing healthy to return to, so nothing is current
        shutil.rmtree(final, ignore_errors=True)  # and the unhealthy version is not left looking installed
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


class UpdateOperations:
    """What the owner can do with updates from the app: see the installed version, install a signed release from a folder they chose, and go back to the previous version. The folder holds exactly
    `manifest.json`, `manifest.sig` and `artefact.zip`; nothing else in it is read, and nothing is fetched from the network here (the channel is a separate seam). The owner's data is never touched."""

    FILES = ("manifest.json", "manifest.sig", "artefact.zip")

    def __init__(self, installer: Installer, public_key: Ed25519PublicKey, healthy: Callable[[Path], bool] = lambda _path: True) -> None:
        self._installer, self._key, self._healthy = installer, public_key, healthy

    def status(self) -> dict[str, object]:
        previous = self._installer._link("previous")
        has_previous = previous.is_symlink() and (self._installer.root / "versions" / os.path.basename(os.readlink(previous))).is_dir()
        return {"installed": self._installer.current_version(), "can_roll_back": has_previous}

    def _read(self, folder: Path, name: str) -> bytes:
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARTEFACT_BYTES:
            raise UpdateError("bad_release_folder")
        return path.read_bytes()

    def install_from(self, folder: Path) -> dict[str, object]:
        manifest, signature, artefact = (self._read(folder, name) for name in self.FILES)
        release = verify_release(manifest, signature, self._key)
        version = self._installer.install(release, artefact, self._healthy)
        return {"installed": version, "restart_needed": True}

    def rollback(self) -> dict[str, object]:
        return {"installed": self._installer.rollback(), "restart_needed": True}
