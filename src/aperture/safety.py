"""Privacy and data-safety guarantees.

* :func:`drive_problem` - refuse to run unless the external drive is really
  mounted, writable and *not* the internal disk.
* :class:`WriteGuard` - the single gatekeeper every file write must pass.
  Originals live in the source photo folder, which is never writable.
* :func:`enable_offline_guard` - block every non-loopback network connection
  inside this Python process (air-gap enforcement).
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

from .config import ENV_INTERNAL, Paths, online_allowed


class SafetyError(PermissionError):
    """Raised when an operation would violate a safety guarantee."""


# --------------------------------------------------------------------------
# Drive validation
# --------------------------------------------------------------------------
def drive_problem(drive: Path) -> str | None:
    """Why the external drive cannot be used right now (``None`` = all good).

    The device check prevents the classic accident where an unmounted or
    mistyped path silently turns into an ordinary folder on the internal disk."""
    if not drive.is_dir():
        return f"{drive} was not found. Connect the external drive and try again."
    if not os.access(drive, os.W_OK):
        return (
            f"{drive} is read-only. Drives formatted as NTFS are read-only on a Mac - reformat to APFS or exFAT in Disk Utility."
        )
    if os.environ.get(ENV_INTERNAL) != "1":
        try:
            device = os.stat(drive).st_dev
            if device in (os.stat("/").st_dev, os.stat(Path.home()).st_dev):
                return f"{drive} is on the internal disk, not an external drive. Aperture will not store anything there."
        except OSError as exc:
            return f"Cannot inspect {drive}: {exc}"
    return None


def require_drive(paths: Paths) -> None:
    problem = drive_problem(paths.drive)
    if problem:
        raise SafetyError(problem)


# --------------------------------------------------------------------------
# Path rules
# --------------------------------------------------------------------------
def is_inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def resolve_photo_dir(paths: Paths, candidate: str | Path) -> Path:
    """The source folder must be on the external drive and not be Aperture's own."""
    path = Path(candidate).expanduser().resolve()
    if not is_inside(path, paths.drive.resolve()):
        raise SafetyError(f"The photo folder must be inside {paths.drive.resolve()}")
    if is_inside(path, paths.root.resolve()):
        raise SafetyError("The photo folder cannot be inside Aperture's own data folder")
    return path


def resolve_export_dir(paths: Paths, candidate: str | Path, photo_dir: str | Path) -> Path:
    """Where copies may go: external drive only; may sit inside the photo folder
    (the scanner skips it) but never inside Aperture's own data."""
    path = Path(candidate).expanduser().resolve()
    if not is_inside(path, paths.drive.resolve()):
        raise SafetyError(f"Exports must stay on the external drive ({paths.drive.resolve()})")
    if is_inside(path, paths.root.resolve()):
        raise SafetyError("The export folder cannot be inside Aperture's own data folder")
    return path


class WriteGuard:
    """Allow writes only inside Aperture's folder or the configured export root.

    Anything else - in particular anything under the source photo folder -
    raises :class:`SafetyError` before a single byte is written."""

    def __init__(self, paths: Paths, export_root: Path | None = None) -> None:
        self._root = paths.root
        self._root_prefix = str(paths.root) + os.sep
        self._root_resolved = paths.root.resolve()
        self._export = export_root.resolve() if export_root else None

    def check(self, path: str | Path) -> Path:
        text = str(path)
        if text.startswith(self._root_prefix):  # fast path for thumbnails etc.
            return Path(path)
        resolved = Path(path).expanduser().resolve()
        if is_inside(resolved, self._root_resolved):
            return resolved
        if self._export is not None and is_inside(resolved, self._export):
            return resolved
        raise SafetyError(f"Refusing to write outside Aperture's folders: {resolved}")


# --------------------------------------------------------------------------
# Offline guard
# --------------------------------------------------------------------------
_LOCAL_NAMES = {"", "localhost", "127.0.0.1", "::1", "0.0.0.0", "::", "ip6-localhost"}


def is_local_host(host: Any) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    name = str(host).strip().lower()
    return name in _LOCAL_NAMES or name.startswith("127.") or name.startswith("::ffff:127.")


def enable_offline_guard() -> bool:
    """Refuse every outbound connection and DNS lookup that is not loopback.

    Returns ``True`` when the guard is active.  It is a no-op (returns
    ``False``) only while ``APERTURE_ALLOW_NETWORK=1`` (model download)."""
    if online_allowed():
        return False
    if getattr(socket, "_aperture_guard", False):
        return True

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo
    real_gethostbyname = socket.gethostbyname

    def check_address(address: Any) -> None:
        if isinstance(address, (str, bytes)):  # AF_UNIX path
            return
        if isinstance(address, tuple) and address and not is_local_host(address[0]):
            raise SafetyError(f"Aperture is air-gapped: blocked connection to {address[0]!r}")

    def connect(self: socket.socket, address: Any) -> None:
        check_address(address)
        return real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        check_address(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not is_local_host(host):
            raise socket.gaierror(socket.EAI_NONAME, f"air-gapped: lookup of {host!r} blocked")
        return real_getaddrinfo(host, *args, **kwargs)

    def gethostbyname(host: Any) -> str:
        if not is_local_host(host):
            raise socket.gaierror(socket.EAI_NONAME, f"air-gapped: lookup of {host!r} blocked")
        return real_gethostbyname(host)

    socket.socket.connect = connect  # type: ignore[method-assign,assignment]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign,assignment]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    socket.gethostbyname = gethostbyname  # type: ignore[assignment]
    socket._aperture_guard = True  # type: ignore[attr-defined]
    return True
