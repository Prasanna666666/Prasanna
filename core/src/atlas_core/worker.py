"""The model worker: a separate process that holds the inference engine and can open no network socket.

It reads one JSON command per line on standard input and answers on a private copy of standard output (anything a library prints goes to standard error, which the parent discards).
Before it imports or loads anything it installs the operating-system network denial (`sandbox.install_network_deny`) and reports the mechanism in its first message; if that cannot
be done it exits and the parent refuses to use it. It never sees a grant, a source or a question: only a prompt string, and it returns only text.

Commands: {"op":"load","path":...} {"op":"unload"} {"op":"stream","prompt":...,"max_tokens":n} {"op":"cancel"} (during a stream) {"op":"quit"}.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import threading
from typing import Any

from . import sandbox


def _engine(spec: str, allow_custom: bool) -> Any:
    if spec == "mlx":
        from .mlx_runtime import MlxEngine

        return MlxEngine()
    if not allow_custom:
        raise SystemExit(3)  # only the built-in engine may be named unless the parent explicitly allows another (tests)
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)()


class _Channel:
    """The protocol on a private copy of standard output, and the commands read from standard input by a background thread (so `cancel` is seen while a stream is running)."""

    def __init__(self) -> None:
        self._out = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
        os.dup2(2, 1)  # a library that prints can no longer corrupt the protocol
        self._lock = threading.Lock()
        self.cancel = threading.Event()
        self._pending: list[dict[str, Any]] = []
        self._condition = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()

    def send(self, message: dict[str, Any]) -> None:
        with self._lock:
            self._out.write(json.dumps(message) + "\n")
            self._out.flush()

    def _read(self) -> None:
        for line in sys.stdin:
            try:
                command = json.loads(line)
            except ValueError:
                continue
            if command.get("op") == "cancel":
                self.cancel.set()
            else:
                self._push(command)
        self._push({"op": "quit"})

    def _push(self, command: dict[str, Any]) -> None:
        with self._condition:
            self._pending.append(command)
            self._condition.notify()

    def next(self) -> dict[str, Any]:
        with self._condition:
            self._condition.wait_for(lambda: bool(self._pending))
            return self._pending.pop(0)


def _handle(engine: Any, channel: _Channel, command: dict[str, Any]) -> bool:
    """Run one command; False means quit."""
    op = command.get("op")
    if op == "quit":
        return False
    if op == "load":
        engine.load(str(command["path"]))
        channel.send({"ok": True})
    elif op == "unload":
        engine.unload()
        channel.send({"ok": True})
    elif op == "stream":
        channel.cancel.clear()
        for chunk in engine.stream(str(command["prompt"]), int(command["max_tokens"])):
            if channel.cancel.is_set():
                break
            channel.send({"chunk": chunk})
        channel.send({"done": True, "cancelled": channel.cancel.is_set()})
    else:
        channel.send({"error": "bad_command"})
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default="mlx")
    parser.add_argument("--allow-custom-engine", action="store_true")
    parser.add_argument("--skip-self-sandbox", action="store_true", help="the parent already launched this under an OS sandbox (macOS sandbox-exec)")
    args = parser.parse_args(argv)
    channel = _Channel()
    try:
        mechanism = "launcher" if args.skip_self_sandbox else sandbox.install_network_deny()
    except sandbox.SandboxUnavailable:
        channel.send({"hello": False})
        return 2
    engine = _engine(args.engine, args.allow_custom_engine)
    channel.send({"hello": True, "network_denied": mechanism})
    while True:
        try:
            if not _handle(engine, channel, channel.next()):
                return 0
        except Exception:  # noqa: BLE001  (an engine error is reported as a code, never as text that could carry content)
            channel.send({"error": "failed"})


if __name__ == "__main__":
    sys.exit(main())
