"""Air-gap guard: this process may talk to loopback and to explicitly trusted LOCAL hosts - nothing else.

Installed at start-up. DNS lookups of any other name are refused, and so is any connect() to an address that is
not loopback or resolved from a trusted local host (e.g. the Ollama bridge inside the private Docker network).
There is no public allowlist: Finance makes no internet requests at all. This is defence in depth next to the
container's internal-only network, not a replacement for it.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any

_local_hosts: set[str] = {"localhost"}
_allowed_ips: set[str] = set()
_installed = False
_orig: dict[str, Any] = {}


class EgressBlocked(OSError):
    pass


def allow_local(host: str) -> None:
    """Trust a host on the private network (e.g. the 'ollama' service in docker compose)."""
    _local_hosts.add(host)


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip.split("%", maxsplit=1)[0]).is_loopback
    except ValueError:
        return False


def install() -> None:
    global _installed
    if _installed:
        return
    _orig["gai"], _orig["connect"], _orig["connect_ex"] = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex

    def gai(host, *a, **k):
        h = host.decode() if isinstance(host, bytes) else host
        if h is None or h in _local_hosts or _is_loopback(h or ""):
            res = _orig["gai"](host, *a, **k)
            if h in _local_hosts:
                _allowed_ips.update(r[4][0] for r in res)
            return res
        raise EgressBlocked(f"blocked DNS lookup for {h!r}: Finance is offline by design")

    def check(addr):
        if isinstance(addr, tuple) and addr and isinstance(addr[0], str):
            ip = addr[0]
            if not (_is_loopback(ip) or ip in _allowed_ips):
                raise EgressBlocked(f"blocked connection to {ip}: not loopback or a trusted local host")

    def connect(self, addr):
        if self.family != getattr(socket, "AF_UNIX", -1):
            check(addr)
        return _orig["connect"](self, addr)

    def connect_ex(self, addr):
        if self.family != getattr(socket, "AF_UNIX", -1):
            check(addr)
        return _orig["connect_ex"](self, addr)

    socket.getaddrinfo = gai
    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    _installed = True


def uninstall() -> None:  # tests only
    global _installed
    if _installed:
        socket.getaddrinfo = _orig["gai"]
        socket.socket.connect = _orig["connect"]  # type: ignore[method-assign]
        socket.socket.connect_ex = _orig["connect_ex"]  # type: ignore[method-assign]
        _installed = False
        _allowed_ips.clear()
