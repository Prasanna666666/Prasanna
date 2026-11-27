"""Putting recovered store keys into the Keychain so that no failure or interruption can leave a working installation half-replaced.

A restore writes several Keychain items (one per store). Overwriting them one by one is not safe: a failure, a failing rollback, or the
process being killed between two writes could leave some live keys new and some old. So the work is split by a durable commit point:

1. **Stage.** Each new key is written to an inactive item (`atlas-staged-<name>`, never read by the Core) and read back. The live items are
   not touched, so any failure here, including a failing clean-up, leaves the working installation exactly as it was.
2. **Commit point.** A journal in the data folder is written atomically with state `committing` and the list of items. It holds item
   names only, never a key.
3. **Commit.** Each live item takes its staged value, is read back, and only then is the staged item removed. The step is idempotent.
4. **Recovery.** Before the Core reads any key, `recover` looks at the journal: `committing` is rolled forward to completion (every staged
   value was verified before the commit point, so the new set is complete); a `staging` journal (interrupted before the commit point) has
   its inactive items discarded. Either way the live keys end as one consistent set: the old one, or the new one.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol

JOURNAL = "restore-keys.journal"
LIVE_PREFIX, STAGED_PREFIX = "atlas-", "atlas-staged-"


class KeyItems(Protocol):
    def read(self, service: str) -> str | None: ...
    def write(self, service: str, value: str) -> None: ...
    def delete(self, service: str) -> None: ...


class KeyRestoreError(Exception):
    """A recovered key did not read back as written. Carries no key."""


def _staged(live: str) -> str:
    return STAGED_PREFIX + live.removeprefix(LIVE_PREFIX)


def _write_journal(data_dir: Path, state: str, services: list[str]) -> None:
    """Atomic and durable: written to a temporary file, flushed to disk, renamed into place, and the folder flushed too."""
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path, temp = data_dir / JOURNAL, data_dir / f".{JOURNAL}.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump({"state": state, "services": services}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    folder = os.open(data_dir, os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def _discard_staged(items: KeyItems, services: Iterable[str]) -> bool:
    """Best effort: an inactive item that cannot be removed now is harmless (the Core never reads it). Returns whether all were removed;
    if not, the journal is kept so the next recovery retries."""
    clean = True
    for live in services:
        try:
            items.delete(_staged(live))
        except Exception:  # noqa: BLE001 - a failed clean-up is retried by the next recovery, never a reason to touch a live key
            clean = False
    return clean


def _commit(items: KeyItems, data_dir: Path, services: list[str]) -> None:
    for live in services:
        value = items.read(_staged(live))
        if value is None:
            continue  # already moved by an earlier, interrupted commit (the staged item is removed only after the live one reads back)
        items.write(live, value)
        if items.read(live) != value:
            raise KeyRestoreError("verify")
        items.delete(_staged(live))
    (data_dir / JOURNAL).unlink(missing_ok=True)


def provision(items: KeyItems, keys: Mapping[str, str], data_dir: Path) -> None:
    """Install `keys` (live item name -> value) as one unit, recoverably. `data_dir` holds the journal for this restore."""
    services = list(keys)
    _write_journal(data_dir, "staging", services)
    try:
        for live, value in keys.items():
            items.write(_staged(live), value)
            if items.read(_staged(live)) != value:
                raise KeyRestoreError("verify")
    except BaseException:
        if _discard_staged(items, services):
            (data_dir / JOURNAL).unlink(missing_ok=True)
        raise
    _write_journal(data_dir, "committing", services)  # the commit point: from here the new set is completed, never abandoned
    _commit(items, data_dir, services)


def recover(items: KeyItems, data_dir: Path) -> str:
    """Finish or undo an interrupted key restore. Returns 'none', 'completed' (rolled forward) or 'discarded' (staging undone)."""
    path = data_dir / JOURNAL
    if not path.exists():
        return "none"
    record = json.loads(path.read_text(encoding="utf-8"))
    services = [str(s) for s in record.get("services", [])]
    if record.get("state") == "committing":
        _commit(items, data_dir, services)
        return "completed"
    if _discard_staged(items, services):
        path.unlink(missing_ok=True)
    return "discarded"
