"""Ask the operating system, from inside the worker, whether it really is confined (macOS). The probes TRY the forbidden things and require the OS to refuse them with a permission error.

This is the one place in the model path that touches a socket, and only to be refused: it lives apart from `sandbox` so the architecture rule that no model module can reach the network
keeps covering `sandbox`, `worker`, `isolated` and the rest.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable


class ConfinementFailed(Exception):
    """A probe was not refused by the operating system: the worker is not confined as claimed."""


def _refused(action: Callable[[], object]) -> bool:
    """True only if the operating system itself refused the action with a permission error (an unconfined process gets a different error or succeeds)."""
    try:
        action()
    except PermissionError:
        return True
    except OSError:
        return False
    return False


def _try_write() -> None:
    path = "/private/tmp/.atlas-sandbox-probe"
    open(path, "w").close()
    os.unlink(path)  # reached only if the write was allowed


def _try_network() -> None:
    probe = socket.socket()
    try:
        failure = probe.connect_ex(("127.0.0.1", 9))
        if failure:
            raise OSError(failure, os.strerror(failure))  # EPERM becomes PermissionError; a closed port (an unconfined process) is ConnectionRefusedError
    finally:
        probe.close()


MAC_CHECKS: dict[str, Callable[[], object]] = {"network": _try_network, "write": _try_write, "private_read": lambda: os.listdir("/Users")}


def verify(checks: dict[str, Callable[[], object]] | None = None) -> str:
    for name, action in (checks or MAC_CHECKS).items():
        if not _refused(action):
            raise ConfinementFailed(name)
    return "launcher"
