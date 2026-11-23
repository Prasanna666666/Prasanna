"""`python -m atlas_core.maintenance`: the owner's own backup, verify, restore-drill and restore commands (Stage 4).

The recovery passphrase is read from standard input (never an argument, never the environment, never printed). The store keys come from the Keychain through the same provider the Core uses, so a backup is made
from, and a restore puts keys back into, the real items. Output is one short line of codes and counts: no path inside the data folder, no key, no content.

    backup   <data-dir> <backup-folder>         make a verified backup (data folder may be in use)
    verify   <backup>                           check a backup's integrity; with the passphrase, its authenticity and every database
    drill    <backup> <data-dir>                restore into a temporary place, check it, and record the drill (allows Finance and Health when the host requires one)
    restore  <backup> <new-data-dir>            restore into an empty place and put the recovered keys into the Keychain
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TextIO

from .backup import BackupError, create_backup, restore_backup, run_restore_drill, verify_backup

KEY_ITEMS = {"tasks.db": "task-store", "designation.db": "designation-store", "edits.db": "edits-store"}
BUNDLE_ITEMS = {"documents_index": "documents-index", "mail_index": "mail-index", "model_record": "model-record"}
EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 1, 64
MIN_ARGS = 2

KeyReader = Callable[[str], str]
KeyWriter = Callable[[Mapping[str, str]], None]
Result = tuple[int, str]


def _passphrase(stream: TextIO) -> str:
    return stream.readline().rstrip("\n")


def _verify(paths: list[Path], phrase: str) -> Result:
    result = verify_backup(paths[0], phrase or None)
    return (
        EXIT_OK if result.ok else EXIT_REFUSED
    ), f"verify: {'ok' if result.ok else 'refused'}{' authenticated' if result.authenticated else ''} {','.join(result.problems)}".rstrip() + "\n"


def _backup(paths: list[Path], phrase: str, read_key: KeyReader) -> Result:
    folder = create_backup(
        paths[0], paths[1], db_keys={n: read_key(i) for n, i in KEY_ITEMS.items()}, keys={n: read_key(i) for n, i in BUNDLE_ITEMS.items()}, passphrase=phrase
    )
    return EXIT_OK, f"backup: ok {folder.name}\n"


def _drill(paths: list[Path], phrase: str) -> Result:
    with TemporaryDirectory(prefix="atldrill") as scratch:
        drill = run_restore_drill(paths[0], phrase, Path(scratch) / "restore", paths[1])
    return (EXIT_OK if drill.ok else EXIT_REFUSED), f"drill: {'ok' if drill.ok else 'refused ' + drill.code}\n"


def _restore(paths: list[Path], phrase: str, write_keys: KeyWriter) -> Result:
    report = restore_backup(paths[0], phrase, paths[1], provision_keys=write_keys)
    return EXIT_OK, f"restore: ok {len(report.files)} files, grants not restored\n"


def run(argv: list[str], *, stdin: TextIO, out: TextIO, read_key: KeyReader, write_keys: KeyWriter) -> int:
    """`read_key(item)` returns the Keychain secret for an item name (creating it if the Core never did); `write_keys(bundle)` puts recovered keys back. Both are the platform seam."""
    if len(argv) < MIN_ARGS or argv[0] not in ("backup", "verify", "drill", "restore"):
        out.write("usage: backup|verify|drill|restore ...\n")
        return EXIT_USAGE
    command, paths = argv[0], [Path(a) for a in argv[1:]]
    phrase = _passphrase(stdin)
    try:
        code, line = {
            "verify": lambda: _verify(paths, phrase),
            "backup": lambda: _backup(paths, phrase, read_key),
            "drill": lambda: _drill(paths, phrase),
            "restore": lambda: _restore(paths, phrase, write_keys),
        }[command]()
    except BackupError as error:
        code, line = EXIT_REFUSED, f"{command}: refused {error.code}\n"
    except (OSError, IndexError):
        code, line = EXIT_REFUSED, f"{command}: refused could_not_complete\n"
    out.write(line)
    return code


def main() -> int:  # pragma: no cover  (the platform wiring: the real Keychain, only meaningful on the owner's machine)
    from .macos import KeychainItems

    items = KeychainItems()

    def write_keys(bundle: Mapping[str, str]) -> None:
        names = {**{f"db:{db}": item for db, item in KEY_ITEMS.items()}, **BUNDLE_ITEMS}
        for key, item in names.items():
            if key in bundle:
                items.write(f"atlas-{item}", bundle[key])

    return run(sys.argv[1:], stdin=sys.stdin, out=sys.stdout, read_key=items.secret, write_keys=write_keys)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
