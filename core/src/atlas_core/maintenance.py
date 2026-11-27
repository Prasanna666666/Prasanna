"""`python -m atlas_core.maintenance`: the owner's own backup, verify, restore-drill and restore commands (Stage 4).

The recovery passphrase is read from standard input (never an argument, never the environment, never printed). The store keys come from the Keychain through the same provider the Core uses, so a backup is made
from, and a restore puts keys back into, the real items. Output is one short line of codes and counts: no path inside the data folder, no key, no content.

    backup   <data-dir> <backup-folder>         make a verified backup (data folder may be in use)
    verify   <backup>                           check a backup's integrity; with the passphrase, its authenticity and every database
    drill    <backup> <data-dir>                restore into a temporary place, check it, and record the drill (allows Finance and Health when the host requires one)
    restore  <backup> <new-data-dir>            restore into an empty place and put the recovered keys into the Keychain
    import-finance <legacy-db> <data-dir>       import the old Finance database's transactions (stdin: its key, or an empty line); the original is only read, never changed
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TextIO

from . import keyrestore
from .backup import BackupError, create_backup, restore_backup, run_restore_drill, verify_backup
from .keyrestore import KeyItems
from .migration import MigrationError, Sink, migrate

KEY_ITEMS = {
    "tasks.db": "task-store",
    "designation.db": "designation-store",
    "edits.db": "edits-store",
    "finance-records.db": "finance-records",
    "health-records.db": "health-records",
}
BUNDLE_ITEMS = {"documents_index": "documents-index", "mail_index": "mail-index", "model_record": "model-record"}
EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 1, 64
MIN_ARGS = 2

KeyReader = Callable[[str], str]
KeyWriter = Callable[[Mapping[str, str]], None]
Result = tuple[int, str]
SinkOpener = Callable[[Path], tuple[Sink, Callable[[], None]]]  # the Finance record store of a data folder, and how to close it


def _no_sink(_data_dir: Path) -> tuple[Sink, Callable[[], None]]:
    raise OSError("no Finance store")


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


def _import_finance(paths: list[Path], legacy_key: str, open_sink: SinkOpener) -> Result:
    sink, close = open_sink(paths[1])
    try:
        result = migrate(paths[0], sink, legacy_key or None)
    finally:
        close()
    return (
        EXIT_OK if result.ok else EXIT_REFUSED
    ), f"import-finance: {'ok' if result.ok else 'refused ' + ','.join(result.problems)} {result.migrated} records\n"


def provision_staged(items: KeyItems, bundle: Mapping[str, str], data_dir: Path) -> None:
    """Put recovered keys into the Keychain recoverably (see keyrestore): staged into inactive items first, then committed past a durable
    journal in `data_dir`, so no failure, failing clean-up or interrupted process leaves the working installation with some keys replaced."""
    names = {**{f"db:{db}": item for db, item in KEY_ITEMS.items()}, **BUNDLE_ITEMS}
    keyrestore.provision(items, {f"atlas-{item}": bundle[key] for key, item in names.items() if key in bundle}, data_dir)


def run(argv: list[str], *, stdin: TextIO, out: TextIO, read_key: KeyReader, write_keys: KeyWriter, open_sink: SinkOpener | None = None) -> int:
    """`read_key(item)` returns the Keychain secret for an item name (creating it if the Core never did); `write_keys(bundle)` puts recovered keys back. Both are the platform seam."""
    if len(argv) < MIN_ARGS or argv[0] not in ("backup", "verify", "drill", "restore", "import-finance"):
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
            "import-finance": lambda: _import_finance(paths, phrase, open_sink or _no_sink),
        }[command]()
    except (BackupError, MigrationError) as error:
        code, line = EXIT_REFUSED, f"{command}: refused {error.code}\n"
    except (OSError, IndexError):
        code, line = EXIT_REFUSED, f"{command}: refused could_not_complete\n"
    out.write(line)
    return code


def main() -> int:  # pragma: no cover  (the platform wiring: the real Keychain, only meaningful on the owner's machine)
    from .macos import KeychainItems

    items = KeychainItems()

    def write_keys(bundle: Mapping[str, str]) -> None:
        provision_staged(items, bundle, Path(sys.argv[3]))  # `restore <backup> <target>`: the journal lives in the restored data folder

    def open_sink(data_dir: Path) -> tuple[Sink, Callable[[], None]]:
        from .finance_calc import MONEY_DOMAIN
        from .recordstore import RecordStore, StoredRecords

        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        store = RecordStore(data_dir / "finance-records.db", items.secret("finance-records"), frozenset({MONEY_DOMAIN}))
        return StoredRecords(store, MONEY_DOMAIN), store.close

    return run(sys.argv[1:], stdin=sys.stdin, out=sys.stdout, read_key=items.secret, write_keys=write_keys, open_sink=open_sink)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
