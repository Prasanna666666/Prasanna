"""`IsolatedEngine`: the model engine in a separate worker process whose network access the operating system denies.

The worker is started with a clean environment (no secrets, no tokens), its standard error discarded, and is trusted only after it reports that the denial is in force; a worker
that cannot enforce it is never used (the engine fails closed with RuntimeFailure `isolation_unavailable`). A dead, silent or slow worker is a RuntimeFailure, never a hang.
What crosses the boundary is a prompt string one way and text the other: no grant, no source, no question outside the prompt, no model context object.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any

from . import sandbox
from .intelligence import RuntimeFailure

STARTUP_SECONDS = 60.0
IDLE_SECONDS = 300.0  # the longest the worker may stay silent while producing (a load of a very large model counts)


class IsolatedEngine:
    def __init__(self, engine: str = "mlx", *, allow_custom_engine: bool = False, python: str | None = None, silence_limit: float = IDLE_SECONDS) -> None:
        self._spec, self._custom, self._python, self._limit = engine, allow_custom_engine, python or sys.executable, silence_limit
        self._proc: subprocess.Popen[bytes] | None = None
        self._buffer = (
            b""  # bytes read from the worker but not yet a whole line (select() cannot see what a buffered reader already holds, so lines are cut here)
        )
        self.network_denied: str | None = None  # the mechanism the worker reported (tests, diagnostics)

    # -- the process -----------------------------------------------------------------------------------------------------------------------
    def _command(self) -> list[str]:
        prefix = sandbox.launch_prefix()
        command = [*prefix, self._python, "-m", "atlas_core.worker", "--engine", self._spec]
        if self._custom:
            command.append("--allow-custom-engine")
        if prefix:
            command.append("--skip-self-sandbox")
        return command

    def _start(self) -> subprocess.Popen[bytes]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        try:
            command = self._command()
        except sandbox.SandboxUnavailable:
            raise RuntimeFailure("isolation_unavailable") from None
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
        env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
        self._buffer = b""
        self._proc = subprocess.Popen(  # noqa: S603
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, env=env, close_fds=True
        )
        hello = self._read(STARTUP_SECONDS)
        if not hello.get("hello"):
            self.close()
            raise RuntimeFailure("isolation_unavailable")
        self.network_denied = str(hello.get("network_denied"))
        return self._proc

    def _read(self, timeout: float) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise RuntimeFailure("worker_gone")
        deadline = time.monotonic() + timeout
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            ready = select.select([proc.stdout], [], [], max(remaining, 0))[0] if remaining > 0 else []
            if not ready:
                self.close()
                raise RuntimeFailure("worker_silent")
            block = os.read(proc.stdout.fileno(), 65536)
            if not block:
                self.close()
                raise RuntimeFailure("worker_gone")
            self._buffer += block
        line, _, self._buffer = self._buffer.partition(b"\n")
        try:
            message = json.loads(line)
        except ValueError:
            self.close()
            raise RuntimeFailure("worker_confused") from None
        if not isinstance(message, dict):
            self.close()
            raise RuntimeFailure("worker_confused")
        return message

    def _send(self, message: dict[str, Any]) -> None:
        proc = self._start()
        try:
            assert proc.stdin is not None
            proc.stdin.write((json.dumps(message) + "\n").encode())
            proc.stdin.flush()
        except (OSError, ValueError):
            self.close()
            raise RuntimeFailure("worker_gone") from None

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(5)
        if proc is not None:
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    stream.close()

    # -- Engine ----------------------------------------------------------------------------------------------------------------------------
    def _ok(self, message: dict[str, Any], limit: float) -> None:
        reply = self._read(limit)
        if not reply.get("ok"):
            raise RuntimeFailure("load_failed" if message["op"] == "load" else "worker_failed")

    def load(self, path: str) -> None:
        self._send({"op": "load", "path": path})
        self._ok({"op": "load"}, self._limit)

    def unload(self) -> None:
        if self._proc is None:
            return
        self._send({"op": "unload"})
        self._ok({"op": "unload"}, STARTUP_SECONDS)

    def stream(self, prompt: str, max_tokens: int) -> Iterator[str]:
        self._send({"op": "stream", "prompt": prompt, "max_tokens": max_tokens})
        finished = False
        try:
            while True:
                reply = self._read(self._limit)
                if "chunk" in reply:
                    yield str(reply["chunk"])
                elif reply.get("done"):
                    finished = True
                    return
                else:
                    finished = True
                    raise RuntimeFailure("inference_failed")
        finally:
            if (
                not finished and self._proc is not None
            ):  # the consumer stopped early: tell the worker, then drain to the end of that stream so the pipe stays in step
                self._cancel()

    def _cancel(self) -> None:
        proc = self._proc
        try:
            assert proc is not None and proc.stdin is not None
            proc.stdin.write((json.dumps({"op": "cancel"}) + "\n").encode())
            proc.stdin.flush()
            while True:
                reply = self._read(STARTUP_SECONDS)
                if reply.get("done") or "error" in reply:
                    return
        except (OSError, RuntimeFailure):
            self.close()
