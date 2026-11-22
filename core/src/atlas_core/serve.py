"""`python -m atlas_core.serve`: run one Core as a child process of the app that owns it.

The app starts this process and gives it a one-time bootstrap code over the child's STANDARD INPUT, a pipe only the two of them hold: never on the command line (visible to every
process of the user), never in the environment, never in a file, never in a log. The Core reads one line, validates its shape, closes standard input and builds itself; it prints
`READY` on standard output once the socket is bound, and stops on SIGTERM or SIGINT. With no code and no enrolled owner it exits without starting (fail closed).
"""

from __future__ import annotations

import argparse
import importlib
import re
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from .app import Core, CoreConfig

CODE_SHAPE = re.compile(r"[A-Za-z0-9_-]{16,64}\Z")
FactoryT = Callable[[Path, Path, str | None], CoreConfig]
EXIT_REFUSED = 4


def _factory(spec: str, allow_custom: bool) -> FactoryT:
    if spec == "host":
        from .host import build_config

        return build_config
    if not allow_custom:
        raise SystemExit(EXIT_REFUSED)  # only the built-in production factory may be named unless the parent explicitly allows another (tests)
    module, _, name = spec.partition(":")
    factory: FactoryT = getattr(importlib.import_module(module), name)
    return factory


def read_code(stream: object) -> str | None:
    """The one line the parent wrote, or None if there is none or it does not have the shape of a code. Never echoed."""
    line = stream.readline().strip() if hasattr(stream, "readline") else ""
    return line if CODE_SHAPE.match(line) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--config-factory", default="host")
    parser.add_argument("--allow-custom-factory", action="store_true")
    args = parser.parse_args(argv)
    code = read_code(sys.stdin)
    sys.stdin.close()
    config = _factory(args.config_factory, args.allow_custom_factory)(Path(args.data_dir), Path(args.socket), code)
    try:
        core = Core(config)
    except ValueError:
        return EXIT_REFUSED  # no owner enrolled and no usable code: it does not start
    core.start()
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stop.set())
    print("READY", flush=True)
    stop.wait()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
