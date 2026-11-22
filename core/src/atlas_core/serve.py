"""`python -m atlas_core.serve`: run one Core as a child process of the app that owns it.

The app starts this process and gives it a one-time bootstrap code over the child's STANDARD INPUT, a pipe only the two of them hold: never on the command line (visible to every
process of the user), never in the environment, never in a file, never in a log. The Core reads one line, validates its shape, closes standard input and builds itself; it prints
`READY` on standard output once the socket is bound, and stops on SIGTERM or SIGINT. With no code and no enrolled owner it exits without starting (fail closed).
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from .app import Core, CoreAlreadyRunning, CoreConfig
from .host import HostOptions

CODE_SHAPE = re.compile(r"[A-Za-z0-9_-]{16,64}\Z")
FactoryT = Callable[[Path, Path, str | None, HostOptions], CoreConfig]
EXIT_REFUSED = 4
EXIT_BUSY = 5  # another Core owns this data folder


def _factory(spec: str, allow_custom: bool) -> FactoryT:
    if spec == "host":
        from .host import build_config

        return build_config
    if not allow_custom:
        raise SystemExit(EXIT_REFUSED)  # only the built-in production factory may be named unless the parent explicitly allows another (tests)
    module, _, name = spec.partition(":")
    factory: FactoryT = getattr(importlib.import_module(module), name)
    return factory


def _source(spec: str | None) -> tuple[str, Path] | None:
    if not spec:
        return None
    name, _, folder = spec.partition("=")
    return (name, Path(folder)) if name and folder else None


def read_code(stream: object) -> str | None:
    """The one line the parent wrote, or None if there is none or it does not have the shape of a code. Never echoed."""
    line = stream.readline().strip() if hasattr(stream, "readline") else ""
    return line if CODE_SHAPE.match(line) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument(
        "--documents-source", help="NAME=FOLDER: the folder designated for the documents source type (NAME is a source type of the policy rules)"
    )
    parser.add_argument("--mail-source", help="NAME=FOLDER: the Apple Mail folder for the mail source type")
    parser.add_argument("--manifest-pubkey", help="the installed public key (32 raw bytes) that signed the model manifest")
    parser.add_argument("--config-factory", default="host")
    parser.add_argument("--allow-custom-factory", action="store_true")
    args = parser.parse_args(argv)
    code = read_code(sys.stdin)
    sys.stdin.close()
    options = HostOptions(_source(args.documents_source), _source(args.mail_source), Path(args.manifest_pubkey) if args.manifest_pubkey else None)
    config = _factory(args.config_factory, args.allow_custom_factory)(Path(args.data_dir), Path(args.socket), code, options)
    try:
        core = Core(config)
    except ValueError:
        return EXIT_REFUSED  # no owner enrolled and no usable code: it does not start
    except CoreAlreadyRunning:
        return EXIT_BUSY  # a live Core has this folder: this one touches nothing
    core.start()
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stop.set())
    print("READY", flush=True)
    parent = os.getppid()

    def orphaned() -> None:  # the app that started this Core is gone (quit, crash, kill): stop at once instead of running on with no one to answer to
        while not stop.wait(0.5):
            if os.getppid() != parent:
                stop.set()

    threading.Thread(target=orphaned, daemon=True).start()
    stop.wait()
    core.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
