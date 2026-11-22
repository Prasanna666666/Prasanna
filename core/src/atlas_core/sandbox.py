"""Operating-system enforcement that a process cannot open a network socket (the model worker's boundary: INTELLIGENCE_AND_PERFORMANCE.md section 5.4, INTERNET_AND_NETWORK_POLICY.md).

Linux: a seccomp filter, installed by the worker on itself before it loads anything, makes `socket()` fail for every domain except AF_UNIX and blocks `io_uring_setup` (which can
create sockets without the `socket` call). The filter cannot be removed (no_new_privs) and is inherited by every thread and child. macOS: the worker is launched under
`sandbox-exec` with a profile that denies network and writes; that path is written from the documentation and has NOT been run (no Mac here), so it is marked as such.
Anything else, or an architecture the filter does not know, FAILS CLOSED: the worker refuses to start instead of running unconfined.
"""

from __future__ import annotations

import ctypes
import os
import platform
import struct
import sys

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
MAC_PROFILE = '(version 1)(deny default)(allow process-exec*)(allow process-fork)(allow sysctl-read)(allow mach-lookup)(allow file-read*)(allow file-write* (literal "/dev/null"))(deny network*)'


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


def launch_prefix() -> list[str]:
    """What must precede the worker's command line so the OS confines it from the start. Empty on Linux (the worker confines itself); `sandbox-exec` on macOS (UNVERIFIED there)."""
    if sys.platform == "darwin":
        exe = "/usr/bin/sandbox-exec"
        if not os.access(exe, os.X_OK):
            raise SandboxUnavailable("sandbox-exec")
        return [exe, "-p", MAC_PROFILE]
    if sys.platform.startswith("linux"):
        return []
    raise SandboxUnavailable("platform")
