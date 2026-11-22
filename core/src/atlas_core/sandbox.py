"""Operating-system enforcement that a process cannot open a network socket (the model worker's boundary: INTELLIGENCE_AND_PERFORMANCE.md section 5.4, INTERNET_AND_NETWORK_POLICY.md).

Linux: a seccomp filter, installed by the worker on itself before it loads anything, makes `socket()` fail for every domain except AF_UNIX and blocks `io_uring_setup` (which can
create sockets without the `socket` call). The filter cannot be removed (no_new_privs) and is inherited by every thread and child. macOS: the worker is launched under
`sandbox-exec` with a profile that denies network and writes; its network denial (TCP connect and UDP send) is exercised by the isolated-worker tests on a macOS CI runner.
Anything else, or an architecture the filter does not know, FAILS CLOSED: the worker refuses to start instead of running unconfined.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import struct
import sys
from collections.abc import Callable, Sequence

from . import confinement

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
AF_UNIX = 1
SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000
EPERM = 1
IO_URING_SETUP = 425  # the same number on x86-64 and arm64
ARCHES = {  # machine -> (AUDIT_ARCH, number of the socket syscall)
    "x86_64": (0xC000003E, 41),
    "aarch64": (0xC00000B7, 198),
}
# The macOS profile. Measured on macOS runners: a deny-by-default profile stops the Metal shader compiler (MLX then reports "No Metal device available"), and a read allow-list that starts
# from "deny everything" aborts Python at start-up, so the profile is allow-by-default with explicit denials: no network, no file writes (except /dev/null), no reading of the places private
# data lives (every user's home folder with Documents, Mail and browser data, external volumes, the temporary folders and root's home) except the model folder and the Python runtime's own
# folders, no executing a program that is not part of the Python runtime, and no Mach lookup of the system services that make network requests for a process. NOT a least-privilege
# profile: reading system files outside those places, other Mach lookups, IOKit and signals stay allowed; the Mach deny list is best effort and not proven complete.
PRIVATE_READ_ROOTS = ("/Users", "/Volumes", "/private/tmp", "/private/var/folders", "/private/var/root", "/home")
NETWORK_SERVICES = (
    "com.apple.dnssd.service",
    "com.apple.SystemConfiguration.configd",
    "com.apple.SystemConfiguration.DNSConfiguration",
    "com.apple.networkd",
    "com.apple.nsurlsessiond",
    "com.apple.nsurlstoraged",
    "com.apple.cfnetwork.cfnetworkagent",
)


def _real(path: str) -> str:
    return os.path.realpath(path)


def mac_profile(read_roots: Sequence[str] = ()) -> str:
    """The sandbox-exec profile text (rules are evaluated last-match-wins, so the exceptions follow the denials they relax)."""
    runtime = {_real(p) for p in (sys.prefix, sys.base_prefix, *(q for q in sys.path if q and os.path.isdir(q)))}
    readable = sorted({*runtime, *map(_real, read_roots)})
    python = sorted(
        {_real(sys.prefix), _real(sys.base_prefix), _real(os.path.dirname(sys.executable))}
    )  # the framework's `python` may re-execute a binary inside its own Python.app
    quote = json.dumps  # an SBPL string is a double-quoted string with C-style escapes
    parts = [
        "(version 1)(allow default)",
        "(deny network*)",
        '(deny file-write*)(allow file-write* (literal "/dev/null"))',
        "(deny file-read-data " + "".join(f"(subpath {quote(p)})" for p in PRIVATE_READ_ROOTS) + ")",
        "(allow file-read-data " + "".join(f"(subpath {quote(p)})" for p in readable) + ")",  # only the model folder and what Python itself needs
        "(deny process-exec*)(allow process-exec* " + "".join(f"(subpath {quote(p)})" for p in python) + ")",  # only programs inside the Python runtime
        "(deny mach-lookup " + "".join(f"(global-name {quote(n)})" for n in NETWORK_SERVICES) + ")",
    ]
    return "".join(parts)


class SandboxUnavailable(RuntimeError):
    """No enforced network denial is available here: the worker must not run."""


def _ins(code: int, jt: int, jf: int, k: int) -> bytes:
    return struct.pack("HBBI", code, jt, jf, k)


def filter_program(arch: int, socket_nr: int) -> bytes:
    """The classic-BPF program: wrong architecture -> kill; io_uring_setup -> EPERM; socket(domain != AF_UNIX) -> EPERM; everything else allowed."""
    ld, jeq, ret = 0x20, 0x15, 0x06
    return b"".join(
        [
            _ins(ld, 0, 0, 4),  # 0: arch
            _ins(jeq, 1, 0, arch),  # 1: right architecture? skip the kill
            _ins(ret, 0, 0, SECCOMP_RET_KILL_PROCESS),  # 2
            _ins(ld, 0, 0, 0),  # 3: syscall number
            _ins(jeq, 0, 1, IO_URING_SETUP),  # 4: io_uring_setup -> 5, else skip to 6
            _ins(ret, 0, 0, SECCOMP_RET_ERRNO | EPERM),  # 5
            _ins(jeq, 1, 0, socket_nr),  # 6: socket -> 8, else 7
            _ins(ret, 0, 0, SECCOMP_RET_ALLOW),  # 7
            _ins(ld, 0, 0, 16),  # 8: first argument (the domain)
            _ins(jeq, 1, 0, AF_UNIX),  # 9: AF_UNIX -> 11, else 10
            _ins(ret, 0, 0, SECCOMP_RET_ERRNO | EPERM),  # 10
            _ins(ret, 0, 0, SECCOMP_RET_ALLOW),  # 11
        ]
    )


def install_network_deny() -> str:
    """Apply the filter to THIS process (and everything it starts). Returns the mechanism name, or raises SandboxUnavailable. Linux only; macOS uses `launch_prefix`."""
    if sys.platform == "darwin":
        return verify_launcher_sandbox()  # the confinement was applied from outside by `sandbox-exec`; this process asks the OS instead of believing anyone
    if not sys.platform.startswith("linux"):
        raise SandboxUnavailable("platform")
    known = ARCHES.get(platform.machine())
    if known is None:
        raise SandboxUnavailable("architecture")
    program = filter_program(*known)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise SandboxUnavailable("no_new_privs")
    buffer = ctypes.create_string_buffer(program, len(program))

    class Fprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]

    fprog = Fprog(len(program) // 8, ctypes.cast(buffer, ctypes.c_void_p))
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0) != 0:
        raise SandboxUnavailable("seccomp")
    return "seccomp"


def verify_launcher_sandbox(checks: dict[str, Callable[[], object]] | None = None) -> str:
    """macOS: the worker must be running under the `sandbox-exec` profile. Nothing the caller says counts (there is no flag for it): `confinement` has the worker attempt a network connect, a
    file write and a read of /Users, and it refuses to run unless the operating system refuses all three. Any other result, including a probe that cannot be made, fails closed."""
    try:
        return confinement.verify(checks)
    except confinement.ConfinementFailed as failure:
        raise SandboxUnavailable(str(failure)) from None


def launch_prefix(read_roots: Sequence[str] = ()) -> list[str]:
    """What must precede the worker's command line so the OS confines it from the start. Empty on Linux (the worker confines itself); `sandbox-exec` on macOS with a profile that lets the
    worker read none of the private places except `read_roots` (the staged model folder) and its Python runtime (network and write denial CI-verified on a macOS runner)."""
    if sys.platform == "darwin":
        exe = "/usr/bin/sandbox-exec"
        if not os.access(exe, os.X_OK):
            raise SandboxUnavailable("sandbox-exec")
        return [exe, "-p", mac_profile(read_roots)]
    if sys.platform.startswith("linux"):
        return []
    raise SandboxUnavailable("platform")
