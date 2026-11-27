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

from .app import Core, CoreAlreadyRunning, CoreConfig, acquire_data_dir
from .host import HostOptions, HostUnavailable, KeychainLocked
from .relay import Relay, RelayRefused

CODE_SHAPE = re.compile(r"[A-Za-z0-9_-]{16,64}\Z")
FactoryT = Callable[[Path, Path, str | None, HostOptions], CoreConfig]
EXIT_REFUSED = 4
EXIT_BUSY = 5  # another Core owns this data folder
EXIT_SHUTDOWN_INCOMPLETE = (
    7  # work was still running when the Core had to stop: the stores were left as they were and the process ends (which releases the folder lock)
)
EXIT_NEEDS_SIGNIN = 6  # the Keychain would not give the store keys: the Mac has not been signed in to since it restarted


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


def _options(args: argparse.Namespace) -> HostOptions:
    """What the host is told about its sources and its own install, from the command line."""
    return HostOptions(
        _source(args.documents_source),
        _source(args.mail_source),
        Path(args.manifest_pubkey) if args.manifest_pubkey else None,
        update_root=Path(args.update_root) if args.update_root else None,
        update_pubkey=Path(args.update_pubkey) if args.update_pubkey else None,
    )


def _stop_on_signal_or_orphaning() -> threading.Event:
    """Set by SIGTERM or SIGINT, or when the app that started this Core is gone (quit, crash, kill): the Core then stops at once instead of running on with no one to answer to."""
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stop.set())
    parent = os.getppid()

    def orphaned() -> None:
        while not stop.wait(0.5):
            if os.getppid() != parent:
                stop.set()

    threading.Thread(target=orphaned, daemon=True).start()
    return stop


def _start_relay(bind: str | None, socket_path: Path) -> Relay | None:
    """The optional remote channel. A bind address that is not private is refused and the Core runs without it."""
    if not bind:
        return None
    host, _, port = bind.rpartition(":")
    try:
        relay = Relay(host, int(port), socket_path)
    except (RelayRefused, ValueError, OSError):
        return None
    relay.start()
    return relay


def _give_up(lock: int) -> None:
    """A start refused before the Core existed: release the folder lock. The lock FILE is deliberately left in place (it is empty and only names the folder's single owner): removing it would let one contender
    hold the old file while another holds a new one at the same path, and both would think they own the folder."""
    os.close(lock)


def _open_core(args: argparse.Namespace, code: str | None, options: HostOptions) -> Core | int:
    """Take the folder, build the config (keys, stores) and the Core. Returns the Core, or the exit status of a start that was refused before anything ran."""
    data_dir = Path(args.data_dir)
    try:
        lock = acquire_data_dir(data_dir)  # first: a start that will lose to another Core touches no Keychain item and opens no store
    except CoreAlreadyRunning:
        return EXIT_BUSY
    try:
        config = _factory(args.config_factory, args.allow_custom_factory)(data_dir, Path(args.socket), code, options)
    except KeychainLocked:
        _give_up(lock)
        return EXIT_NEEDS_SIGNIN  # no key provisioned, nothing opened, bound or written (only the empty lock file exists)
    except HostUnavailable:
        _give_up(lock)
        return EXIT_REFUSED
    except BaseException:
        _give_up(lock)  # any other failure of the factory: the lock is released, never leaked to a process that goes on running
        raise
    config.data_dir_lock = lock
    try:
        return Core(config)
    except ValueError:
        return EXIT_REFUSED  # no owner enrolled and no usable code: it does not start
    except CoreAlreadyRunning:
        return EXIT_BUSY  # a live Core has this folder: this one touches nothing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument(
        "--documents-source", help="NAME=FOLDER: the folder designated for the documents source type (NAME is a source type of the policy rules)"
    )
    parser.add_argument("--mail-source", help="NAME=FOLDER: the Apple Mail folder for the mail source type")
    parser.add_argument("--manifest-pubkey", help="the installed public key (32 raw bytes) that signed the model manifest")
    parser.add_argument("--update-root", help="the folder that holds the app's own versions (versions/, current, previous)")
    parser.add_argument("--update-pubkey", help="the installed public key (32 raw bytes) that signs releases")
    parser.add_argument(
        "--relay-bind", help="HOST:PORT on a private or VPN address where a paired phone may reach the Core (off by default; a public address is refused)"
    )
    parser.add_argument("--config-factory", default="host")
    parser.add_argument("--allow-custom-factory", action="store_true")
    args = parser.parse_args(argv)
    code = read_code(sys.stdin)
    sys.stdin.close()
    options = _options(args)
    opened = _open_core(args, code, options)
    if isinstance(opened, int):
        return opened
    core = opened
    core.start()
    relay = _start_relay(args.relay_bind, Path(args.socket))
    stop = _stop_on_signal_or_orphaning()
    print("READY", flush=True)
    stop.wait()
    if relay is not None:
        relay.close()
    return 0 if core.close() else EXIT_SHUTDOWN_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
