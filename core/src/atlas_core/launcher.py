"""The parent side of `serve`: start a Core as a child process and hand it a fresh one-time bootstrap code over its standard input (the Python counterpart of the app's launcher).

The code lives in this object's memory only. `forget_code()` drops it once the owner is enrolled.
"""

from __future__ import annotations

import os
import secrets
import select
import subprocess
import sys
import time
from pathlib import Path


class LaunchFailed(RuntimeError):
    """The Core did not come up. Carries no output of the child."""


class CoreProcess:
    def __init__(
        self,
        data_dir: Path,
        socket_path: Path,
        *,
        config_factory: str = "host",
        allow_custom_factory: bool = False,
        python: str | None = None,
        extra_args: tuple[str, ...] = (),
    ) -> None:
        self.data_dir, self.socket_path = data_dir, socket_path
        self._factory, self._custom, self._python = config_factory, allow_custom_factory, python or sys.executable
        self._extra = extra_args  # e.g. --documents-source documents=FOLDER; never a secret (the code goes over stdin)
        self.bootstrap_code: str | None = None
        self.process: subprocess.Popen[bytes] | None = None

    def start(self, timeout: float = 60.0) -> str:
        """Start the Core; returns the socket path once the child says READY. Raises LaunchFailed if it refuses, dies or is too slow."""
        code = secrets.token_urlsafe(24)  # 32 characters of the allowed alphabet
        command = [
            self._python,
            "-m",
            "atlas_core.serve",
            "--data-dir",
            str(self.data_dir),
            "--socket",
            str(self.socket_path),
            "--config-factory",
            self._factory,
        ]
        if self._custom:
            command.append("--allow-custom-factory")
        command.extend(self._extra)
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
        env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
        self.process = subprocess.Popen(  # noqa: S603
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, bufsize=0, close_fds=True
        )
        assert self.process.stdin is not None and self.process.stdout is not None
        try:
            self.process.stdin.write((code + "\n").encode())
            self.process.stdin.close()
        except OSError:
            self._kill()
            raise LaunchFailed("handoff") from None
        deadline, seen = time.monotonic() + timeout, b""
        while b"READY" not in seen:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                self._kill()
                raise LaunchFailed("timeout")
            block = os.read(self.process.stdout.fileno(), 4096)
            if not block:
                self._kill()
                raise LaunchFailed("exited")
            seen += block
        self.bootstrap_code = code
        return str(self.socket_path)

    def forget_code(self) -> None:
        self.bootstrap_code = None

    def _kill(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
        if self.process is not None:
            self.process.wait(5)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(5)
