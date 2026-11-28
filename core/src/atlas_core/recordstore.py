"""The owner's own Calendar, Contacts and Notes records, writable, versioned and undoable (Stage 5; PRD 4.4: editing notes, creating or moving own calendar events and reversible local changes never prompt).

An encrypted store of its own (its own file and key). Every change is an append-only history row holding the full before and after, so:

* **Undo is exact.** `undo` restores the `before` of the change, but only while the record is still at the version that change produced (otherwise another change happened since: a conflict, never a guess).
* **Edits are checked.** A change names the version it was made against; a stale version is a conflict, so two writers cannot silently overwrite each other.
* **Deleting is soft.** A deleted record stays in the history and can be restored. Removing a record for good is a different, irreversible operation that this store does not offer: it is an approval-gated
  action elsewhere (PRD 4.4 category 3).
* **Originals are untouched.** Records imported from a source are never modified; this store is an overlay of the owner's own edits, with each row's origin recorded.

Nothing here sends anything anywhere.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kit.db import connect

from .mail import Listed, ListPage
from .records import Record, RecordError, as_message

SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (record_id TEXT PRIMARY KEY, domain TEXT NOT NULL, version INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL, title TEXT NOT NULL, fields TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history (seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, version INTEGER NOT NULL, op TEXT NOT NULL, before TEXT, after TEXT, at TEXT NOT NULL, origin TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS history_record ON history(record_id);
CREATE TABLE IF NOT EXISTS audit_anchor (one INTEGER PRIMARY KEY CHECK (one = 1), seq INTEGER NOT NULL, digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS receipts (action_id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL, result TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
"""


class StoreError(Exception):
    """A change was refused. Carries a code (not_found, exists, conflict, nothing_to_undo, wrong_domain) and never record content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Stored:
    record: Record
    version: int
    deleted: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _dump(record: Record | None, deleted: bool = False) -> str | None:
    if record is None:
        return None
    return json.dumps(
        {"id": record.record_id, "domain": record.domain, "date": record.date, "title": record.title, "fields": dict(record.fields), "deleted": deleted},
        sort_keys=True,
    )


def _load(text: str) -> tuple[Record, bool]:
    d = json.loads(text)
    return Record(d["id"], d["domain"], d["date"], d["title"], d["fields"]), bool(d["deleted"])


class RecordStore:
    def __init__(self, path: Path, key: str | None, domains: frozenset[str], clock: Callable[[], datetime] = _now) -> None:
        self._domains, self._clock, self._lock = domains, clock, threading.RLock()
        self._conn = connect(path, key)
        self._conn.isolation_level = None
        with self._lock:
            if self._conn.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:  # refuse BEFORE any DDL: an older app must not alter a newer store
                self._conn.close()
                raise StoreError("newer_store")
            self._conn.executescript(_SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # -- action receipts (ATLAS-ACT-019): what an executed action needs for its undo, kept in this encrypted store so undo survives a restart ----
    def put_receipt(self, action_id: str, name: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO receipts (action_id, name, payload, result) VALUES (?,?,?,?)",
                (action_id, name, json.dumps(payload, sort_keys=True), json.dumps(result, sort_keys=True)),
            )

    def receipt(self, action_id: str) -> tuple[str, dict[str, Any], dict[str, Any], bool] | None:
        with self._lock:
            row = self._conn.execute("SELECT name, payload, result, undone FROM receipts WHERE action_id=?", (action_id,)).fetchone()
        return None if row is None else (str(row["name"]), json.loads(row["payload"]), json.loads(row["result"]), bool(row["undone"]))

    # -- the audit anchor (ATLAS-ACT-019): the last audit entry's sequence and digest, kept OUTSIDE the audit file, so a deleted or truncated
    # audit is told apart from a first run ----------------------------------------------------------------------------------------------------
    def set_audit_anchor(self, seq: int, digest: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_anchor (one, seq, digest) VALUES (1,?,?) ON CONFLICT(one) DO UPDATE SET seq=excluded.seq, digest=excluded.digest",
                (seq, digest),
            )

    def audit_anchor(self) -> tuple[int, str] | None:
        with self._lock:
            row = self._conn.execute("SELECT seq, digest FROM audit_anchor WHERE one=1").fetchone()
        return None if row is None else (int(row["seq"]), str(row["digest"]))

    def mark_undone(self, action_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE receipts SET undone=1 WHERE action_id=?", (action_id,))

    def close(self) -> None:
        self._conn.close()

    # -- reading --------------------------------------------------------------------------------------------------------------------------------
    def get(self, record_id: str, *, include_deleted: bool = False) -> Stored:
        with self._lock:
            row = self._conn.execute("SELECT * FROM records WHERE record_id=?", (record_id,)).fetchone()
        if row is None or (row["deleted"] and not include_deleted):
            raise StoreError("not_found")
        return Stored(Record(row["record_id"], row["domain"], row["date"], row["title"], json.loads(row["fields"])), int(row["version"]), bool(row["deleted"]))

    def in_domain(self, domain: str) -> list[Stored]:
        with self._lock:
            rows = self._conn.execute("SELECT record_id FROM records WHERE domain=? AND deleted=0 ORDER BY date, record_id", (domain,)).fetchall()
        return [self.get(r["record_id"]) for r in rows]

    def history(self, record_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT seq, version, op, at, origin, undone FROM history WHERE record_id=? ORDER BY seq", (record_id,)).fetchall()
        return [dict(r) for r in rows]

    # -- writing: one transaction = the row and its history entry --------------------------------------------------------------------------------
    def _check(self, record: Record) -> None:
        if record.domain not in self._domains:
            raise StoreError("wrong_domain")

    def _write(self, op: str, before: str | None, after: Record, deleted: bool, version: int, origin: str, also: Callable[[int], None] | None = None) -> int:
        """`also(new_seq)` runs inside the same transaction, after the history row exists: all of it commits, or none of it."""
        at = self._clock().isoformat()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO records (record_id, domain, version, deleted, date, title, fields) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(record_id) DO UPDATE SET version=excluded.version, deleted=excluded.deleted, date=excluded.date, title=excluded.title, fields=excluded.fields",
                (after.record_id, after.domain, version, int(deleted), after.date, after.title, json.dumps(dict(after.fields), sort_keys=True)),
            )
            cursor = self._conn.execute(
                "INSERT INTO history (record_id, version, op, before, after, at, origin) VALUES (?,?,?,?,?,?,?)",
                (after.record_id, version, op, before, _dump(after, deleted), at, origin),
            )
            if also is not None:
                also(int(cursor.lastrowid or 0))
            self._conn.execute("COMMIT")
            return int(cursor.lastrowid or 0)
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise

    def create(self, record: Record, origin: str = "owner") -> int:
        """Returns the history sequence number of the change (for undo)."""
        self._check(record)
        with self._lock:
            if self._conn.execute("SELECT 1 FROM records WHERE record_id=?", (record.record_id,)).fetchone():
                raise StoreError("exists")
            return self._write("create", None, record, False, 1, origin)

    def update(
        self,
        record_id: str,
        expected_version: int,
        *,
        title: str | None = None,
        date: str | None = None,
        fields: dict[str, str] | None = None,
        origin: str = "owner",
    ) -> int:
        with self._lock:
            current = self.get(record_id)
            if current.version != expected_version:
                raise StoreError("conflict")
            merged = {**current.record.fields, **(fields or {})}
            try:
                after = Record(record_id, current.record.domain, date or current.record.date, title or current.record.title, merged)
            except RecordError:
                raise StoreError("invalid") from None
            return self._write("update", _dump(current.record), after, False, current.version + 1, origin)

    def delete(self, record_id: str, expected_version: int, origin: str = "owner") -> int:
        """Soft delete: the record is hidden and stays in the history, and undo restores it."""
        with self._lock:
            current = self.get(record_id)
            if current.version != expected_version:
                raise StoreError("conflict")
            return self._write("delete", _dump(current.record), current.record, True, current.version + 1, origin)

    def undo(self, seq: int, origin: str = "owner", receipt: str | None = None) -> int:
        """Reverse exactly the change `seq`, if it is the record's latest change and not already undone. The reversal, both history marks and, with
        `receipt`, that action receipt's undone mark are ONE transaction (UC-L14): an interruption leaves all of it or none of it."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM history WHERE seq=?", (seq,)).fetchone()
            if row is None or row["undone"]:
                raise StoreError("nothing_to_undo")
            latest = self._conn.execute("SELECT max(seq) FROM history WHERE record_id=? AND undone=0", (row["record_id"],)).fetchone()[0]
            if latest != seq:
                raise StoreError("conflict")  # something changed it after this change: undo would guess
            current = self.get(row["record_id"], include_deleted=True)
            if row["before"] is None:  # undoing a create hides the record (it stays in the history)
                after, deleted, op = current.record, True, "undo_create"
            else:
                after, deleted = _load(row["before"])
                op = "undo_" + row["op"]

            def marks(new_seq: int) -> None:
                self._conn.execute("UPDATE history SET undone=1 WHERE seq IN (?,?)", (seq, new_seq))
                if receipt is not None:
                    self._conn.execute("UPDATE receipts SET undone=1 WHERE action_id=?", (receipt,))

            return self._write(op, row["after"], after, deleted, current.version + 1, origin, also=marks)


class StoredRecords:
    """A durable record SOURCE over the store: it presents one domain's records through the same seam as Mail (`list_page`, `read`), newest first, so the guarded index can take them in, and it accepts
    records for a migration (`put`: create or, if the id exists with different content, refuse as a conflict). Deleted records are not listed."""

    def __init__(self, store: RecordStore, domain: str) -> None:
        self._store, self.domain = store, domain

    @property
    def records(self) -> dict[str, Record]:
        return {s.record.record_id: s.record for s in self._store.in_domain(self.domain)}

    def put(self, record: Record) -> None:
        try:
            self._store.create(record, origin="migration")
        except StoreError as error:
            if error.code != "exists":
                raise
            self._restore_rolled_back(record.record_id)  # a retry after a rolled-back import brings back what the rollback took away, and nothing else
            if self._store.get(record.record_id).record != record:
                raise

    def _restore_rolled_back(self, record_id: str) -> bool:
        """Undo a deletion that was made by a migration rollback (and only that): the history says who deleted it."""
        last = self._store.history(record_id)[-1]
        if last["op"] != "delete" or last["origin"] != "migration_rollback" or last["undone"]:
            return False
        self._store.undo(last["seq"], origin="migration")
        return True

    def remove(self, record_id: str) -> None:
        """Take back a record this import created (soft: the history keeps it, as for every delete). Used only to roll a failed import back."""
        try:
            self._store.delete(record_id, self._store.get(record_id).version, origin="migration_rollback")
        except StoreError:
            return

    def list_page(self, cursor: str | None, limit: int) -> Any:
        items = sorted(self._store.in_domain(self.domain), key=lambda s: (s.record.date, s.record.record_id), reverse=True)
        start = int(cursor or 0)
        page = items[start : start + limit]
        listed = [Listed(s.record.record_id, f"v{s.version}", s.record.date) for s in page]
        return ListPage(listed, str(start + limit) if start + limit < len(items) else None)

    def read(self, message_id: str) -> dict[str, str] | None:
        try:
            return as_message(self._store.get(message_id).record)
        except StoreError:
            return None
