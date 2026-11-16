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
        # In the sandbox the photo folder (possibly the whole drive) is read-only on purpose; Aperture only ever writes inside
        # its own folder, so that is what must be writable there.
        own = drive / "Aperture"
        if not (os.environ.get("APERTURE_SANDBOXED") == "1" and own.is_dir() and os.access(own, os.W_OK)):
            return f"{drive} is read-only. Drives formatted as NTFS are read-only on a Mac - reformat to APFS or exFAT in Disk Utility."
    if os.environ.get(ENV_INTERNAL) != "1":
        try:
            device = os.stat(drive).st_dev
            if device in (os.stat("/").st_dev, os.stat(Path.home()).st_dev):
                return f"{drive} is on the internal disk, not an external drive. Aperture will not store anything there."
        except OSError as exc:
            return f"Cannot inspect {drive}: {exc}"
    return None


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


def trusted_hosts() -> set[str]:
    """Extra *private-network* hostnames (e.g. the 'ollama' bridge in Docker) from APERTURE_TRUSTED_HOSTS.

    Empty by default, so a normal install stays loopback-only. Names only - never a public host."""
    return {h.strip().lower() for h in os.environ.get("APERTURE_TRUSTED_HOSTS", "").split(",") if h.strip()}


class _Guard:
    """The replacements for the socket calls that reach out: each checks where it is going first, and only then calls the real one."""

    def __init__(self) -> None:
        self.real_connect = socket.socket.connect
        self.real_connect_ex = socket.socket.connect_ex
        self.real_getaddrinfo = socket.getaddrinfo
        self.real_gethostbyname = socket.gethostbyname
        self.trusted = trusted_hosts()
        self.trusted_ips: set[str] = set()

    def check_address(self, address: Any) -> None:
        if isinstance(address, (str, bytes)):  # AF_UNIX path
            return
        if isinstance(address, tuple) and address and not is_local_host(address[0]) and address[0] not in self.trusted_ips:
            raise SafetyError(f"Aperture is air-gapped: blocked connection to {address[0]!r}")

    def _blocked_lookup(self, host: Any) -> socket.gaierror:
        return socket.gaierror(socket.EAI_NONAME, f"air-gapped: lookup of {host!r} blocked")

    def connect(self, sock: socket.socket, address: Any) -> None:
        self.check_address(address)
        return self.real_connect(sock, address)

    def connect_ex(self, sock: socket.socket, address: Any) -> int:
        self.check_address(address)
        return self.real_connect_ex(sock, address)

    def getaddrinfo(self, host: Any, *args: Any, **kwargs: Any) -> Any:
        if str(host).lower() in self.trusted:
            result = self.real_getaddrinfo(host, *args, **kwargs)
            self.trusted_ips.update(str(r[4][0]) for r in result)
            return result
        if not is_local_host(host):
            raise self._blocked_lookup(host)
        return self.real_getaddrinfo(host, *args, **kwargs)

    def gethostbyname(self, host: Any) -> str:
        if str(host).lower() in self.trusted:
            ip = self.real_gethostbyname(host)
            self.trusted_ips.add(ip)
            return ip
        if not is_local_host(host):
            raise self._blocked_lookup(host)
        return self.real_gethostbyname(host)


def enable_offline_guard() -> bool:
    """Refuse every outbound connection and DNS lookup that is not loopback.

    Returns ``True`` when the guard is active.  It is a no-op (returns
    ``False``) only while ``APERTURE_ALLOW_NETWORK=1`` (model download)."""
    if online_allowed():
        return False
    if getattr(socket, "_aperture_guard", False):
        return True
    guard = _Guard()

    def connect(sock: socket.socket, address: Any) -> None:
        return guard.connect(sock, address)

    def connect_ex(sock: socket.socket, address: Any) -> int:
        return guard.connect_ex(sock, address)

    socket.socket.connect = connect  # type: ignore[method-assign,assignment]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign,assignment]
    socket.getaddrinfo = guard.getaddrinfo  # type: ignore[assignment]
    socket.gethostbyname = guard.gethostbyname  # type: ignore[assignment]
    socket._aperture_guard = True  # type: ignore[attr-defined]
    return True
