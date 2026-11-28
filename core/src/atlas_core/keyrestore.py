"""Putting recovered store keys into the Keychain so that no failure, interruption or second data folder is left half-replaced.

The store keys are account-wide Keychain items (`atlas-<name>`): one owner, one installation (PRD). So a restore is one account-wide,
serialized transaction, and the installation that owns the live keys is recorded:

1. **Ownership.** `atlas-installation` names the data folder whose files the live keys protect; every start records it add-only (`claim`).
   A restore into a different folder is refused while that folder still holds files, so a working installation is never orphaned. When no
   owner is recorded but live keys exist, ownership is unknown and the restore is refused too.
2. **Serialize.** Any earlier interrupted restore is finished or undone first. The journal (`atlas-restore-journal`, a Keychain item, so
   every data folder's start sees it) is added only if absent and read back: a second restore running at the same time is refused.
3. **Stage.** Each new key is written to an inactive item bound to this transaction (`atlas-staged-<tx>-<name>`, never read by the Core)
   and read back. Live items are not touched, so any failure here, including a failing clean-up, leaves the working installation as it was.
4. **Commit point.** The journal is rewritten with state `committing`. It holds item names, the transaction and the target folder only,
   never a key.
5. **Commit.** Each live item takes its staged value and is read back; the journal records it as promoted; only then is the staged item
   removed. A staged item that is missing and was never recorded as promoted is an error, never taken as done. Last, ownership moves to the
   target and the journal is removed. Every step can be repeated.
6. **Recovery.** Before the Core reads any key (in any data folder), `recover` finishes a `committing` journal and undoes a `staging` one,
   so the live keys are always one consistent set, the old one or the new one, with the owner recorded to match.

Every step that reads or changes the journal, the owner record or the live keys runs under one account-wide, cross-process lock (`guard`):
a restore holds it from its first recovery to its last promotion, and a starting Core holds it across recovery, the ownership check and
its key reads (`open_keys`). So a live transaction is never mistaken for an interrupted one, and two recoveries never run at once.
A start refuses a data folder that does not own the live keys (`not_owner`) unless the recorded owner no longer holds files and this folder
is new. When the commit point's write may have persisted but cannot be confirmed, the journal is read again under the same lock: the target's
files are kept unless the journal is confirmed not to have reached the commit point.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
ACCOUNT_LOCK = Path.home() / "Library" / "Application Support" / "Atlas" / "key-restore.lock"  # one per account, like the keys
LOCK_WAIT = 30.0

JOURNAL_ITEM, OWNER_ITEM = "atlas-restore-journal", "atlas-installation"
LIVE_PREFIX, STAGED_PREFIX = "atlas-", "atlas-staged-"


class KeyItems(Protocol):
    def read(self, service: str) -> str | None: ...
    def write(self, service: str, value: str) -> None: ...
    def delete(self, service: str) -> None: ...
    def add_if_absent(self, service: str, value: str) -> None: ...


class KeyRestoreError(Exception):
    """A key restore was refused or could not be verified. `code` names why; carries no key."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class KeyCommitIncomplete(KeyRestoreError):
    """Raised after the commit point: the new key set is complete and the next start's recovery finishes installing it, so the restored files
    that match it must be kept."""


def _staged(tx: str, live: str) -> str:
    return f"{STAGED_PREFIX}{tx}-{live.removeprefix(LIVE_PREFIX)}"


def _journal(items: KeyItems) -> dict[str, Any] | None:
    raw = items.read(JOURNAL_ITEM)
    if raw is None:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        raise KeyRestoreError("journal_unreadable") from None
    if not isinstance(record, dict) or not isinstance(record.get("tx"), str) or not isinstance(record.get("services"), list):
        raise KeyRestoreError("journal_unreadable")
    return record


def _save(items: KeyItems, record: dict[str, Any]) -> None:
    text = json.dumps(record, sort_keys=True)
    items.write(JOURNAL_ITEM, text)
    if items.read(JOURNAL_ITEM) != text:
        raise KeyRestoreError("verify")


def _discard_staged(items: KeyItems, tx: str, services: Iterable[str]) -> bool:
    """Best effort: an inactive item that cannot be removed now is harmless (the Core never reads it). Returns whether all were removed; if not,
    the journal is kept so the next recovery retries."""
    clean = True
    for live in services:
        try:
            items.delete(_staged(tx, live))
        except Exception:  # noqa: BLE001 - a failed clean-up is retried by the next recovery, never a reason to touch a live key
            clean = False
    return clean


def _commit(items: KeyItems, record: dict[str, Any]) -> None:
    tx, promoted = record["tx"], record.setdefault("promoted", [])
    for live in [str(s) for s in record["services"]]:
        if live not in promoted:
            value = items.read(_staged(tx, live))
            if value is None:
                raise KeyRestoreError("staged_missing")  # never promoted and not staged: the set cannot be completed, so nothing is assumed
            items.write(live, value)
            if items.read(live) != value:
                raise KeyRestoreError("verify")
            promoted.append(live)
            _save(items, record)
        items.delete(_staged(tx, live))
    target = str(record["target"])
    items.write(OWNER_ITEM, target)
    if items.read(OWNER_ITEM) != target:
        raise KeyRestoreError("verify")
    items.delete(JOURNAL_ITEM)


FOLDER_LOCK = "core.lock"  # the data-folder lock a starting Core takes first (app.acquire_data_dir); it protects nothing under a key


def _holds_files(folder: Path) -> bool:
    return folder.is_dir() and any(entry.name != FOLDER_LOCK for entry in folder.iterdir())


@contextmanager
def guard(lock: Path, wait: float = LOCK_WAIT) -> Iterator[None]:
    """The account-wide, cross-process lock around every key-restore step. Released when the process ends, so a crash never leaves it held."""
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise KeyRestoreError("busy") from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def verify_owner(items: KeyItems, data_dir: Path) -> None:
    """Called under `guard`. Records, add-only, that this folder owns the live keys (the first start, or an installation from before ownership
    was recorded), then refuses unless it really does. A new, empty folder takes over only from a recorded owner that no longer holds files."""
    here = str(data_dir.resolve())
    items.add_if_absent(OWNER_ITEM, here)
    owner = items.read(OWNER_ITEM)
    if owner == here:
        return
    if owner is None:
        raise KeyRestoreError("verify")
    if _holds_files(Path(owner)) or _holds_files(data_dir):
        raise KeyRestoreError("not_owner")  # the keys protect another folder's files, or this folder's files are not under these keys
    items.write(OWNER_ITEM, here)
    if items.read(OWNER_ITEM) != here:
        raise KeyRestoreError("verify")


def open_keys(items: KeyItems, data_dir: Path, lock: Path | None, read: Callable[[], T]) -> T:
    """A starting Core's whole key step under the lock: finish or undo an interrupted restore, verify that this folder owns the keys, read them."""
    with guard(lock or ACCOUNT_LOCK):
        recover(items)
        verify_owner(items, data_dir)
        return read()


def _commit_point_persisted(items: KeyItems, record: dict[str, Any]) -> bool:
    """Whether the `committing` journal may be in the Keychain after its write could not be confirmed: true unless it reads back as not committed."""
    try:
        stored = _journal(items)
    except Exception:  # noqa: BLE001 - unreadable: it may have persisted, so the restored files are kept for recovery to resolve
        return True
    return stored is not None and stored.get("tx") == record["tx"] and stored.get("state") == "committing"


def provision(items: KeyItems, keys: Mapping[str, str], target: Path, lock: Path | None = None) -> None:
    """Install `keys` (live item name -> value) as one unit for the installation in `target`, recoverably and serialized account-wide."""
    with guard(lock or ACCOUNT_LOCK):
        _provision(items, keys, target)


def _provision(items: KeyItems, keys: Mapping[str, str], target: Path) -> None:
    recover(items)  # an earlier interrupted restore is finished or undone before this one starts
    target, services = target.resolve(), list(keys)
    owner = items.read(OWNER_ITEM)
    if owner is None:
        if any(items.read(live) for live in services):
            raise KeyRestoreError("owner_unknown")  # live keys whose installation is unrecorded: they may protect a working folder
    elif Path(owner) != target and _holds_files(Path(owner)):
        raise KeyRestoreError("another_installation")  # replacing the keys would orphan that folder's files
    record: dict[str, Any] = {"tx": secrets.token_hex(8), "state": "staging", "target": str(target), "services": services, "promoted": []}
    items.add_if_absent(JOURNAL_ITEM, json.dumps(record, sort_keys=True))
    if _journal(items) != record:
        raise KeyRestoreError("restore_in_progress")  # another restore added its journal first
    tx = record["tx"]
    try:
        for live, value in keys.items():
            items.write(_staged(tx, live), value)
            if items.read(_staged(tx, live)) != value:
                raise KeyRestoreError("verify")
    except BaseException:
        if _discard_staged(items, tx, services):
            items.delete(JOURNAL_ITEM)
        raise
    record["state"] = "committing"
    try:
        _save(items, record)  # the commit point: from here the new set is completed, never abandoned
    except Exception as error:
        if _commit_point_persisted(items, record):
            raise KeyCommitIncomplete("commit_unconfirmed") from error  # kept: recovery under the lock finishes it
        if _discard_staged(items, tx, services):
            items.delete(JOURNAL_ITEM)
        raise
    try:
        _commit(items, record)
    except Exception as error:
        raise KeyCommitIncomplete("commit_incomplete") from error


def recover(items: KeyItems) -> str:
    """Called under `guard`. Finish or undo an interrupted key restore, whichever data folder is starting. Returns 'none', 'completed' (rolled
    forward) or 'discarded'."""
    record = _journal(items)
    if record is None:
        return "none"
    if record.get("state") == "committing":
        _commit(items, record)
        return "completed"
    if _discard_staged(items, record["tx"], [str(s) for s in record["services"]]):
        items.delete(JOURNAL_ITEM)
    return "discarded"
