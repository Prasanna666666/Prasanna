"""Durable task state in a NEW, separate, additive, encrypted store (its own file, its own key). It never touches an existing database or key;
deleting the file rolls the whole thing back.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kit.db import EncryptionError, connect

from .contracts import validate
from .errors import CoreError
from .events import new_id
from .rules import Rules, load_rules

SCHEMA_VERSION = 1
KEY_ENV, KEY_FILE_ENV = "ATLAS_TASK_KEY", "ATLAS_TASK_KEY_FILE"
KEYCHAIN_ITEM = "atlas-task-key"  # the dedicated Keychain item that supplies the key on the Mac (provisioning script: not part of this stage)
STEPS = ("none", "policy_checked", "retrieved", "drafted", "verified")
TERMINAL = frozenset({"completed", "partially_completed", "failed", "cancelled", "expired"})
_ANY_END = {"failed", "cancelled", "expired"}
TRANSITIONS: dict[str, frozenset[str]] = {
    "requested": frozenset({"policy_checked"} | _ANY_END),
    "policy_checked": frozenset({"queued"} | _ANY_END),
    "queued": frozenset({"running"} | _ANY_END),
    "running": frozenset({"retrieved", "queued"} | _ANY_END),
    "retrieved": frozenset({"drafted", "queued"} | _ANY_END),
    "drafted": frozenset({"verified", "queued"} | _ANY_END),
    "verified": frozenset({"completed", "partially_completed", "queued"} | _ANY_END),
    **{state: frozenset() for state in TERMINAL},
}
INTERRUPTED = ("running", "retrieved", "drafted", "verified")
STALE_EARLY = ("requested", "policy_checked")


class StoreKeyError(EncryptionError):
    """The task store has no key of its own."""


def task_store_key() -> str:
    """The task store's own key: from a file or the environment, never shared with any other database."""
    path = os.environ.get(KEY_FILE_ENV)
    key = Path(path).read_text().strip() if path else os.environ.get(KEY_ENV, "")
    if not key:
        raise StoreKeyError(f"No key for the task store ({KEY_ENV} or {KEY_FILE_ENV}).")
    return key


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _hash_request(request: dict[str, Any]) -> str:
    keys = {k: request[k] for k in ("objective", "source_scope", "budget")}
    return hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()


DDL = """
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY, state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deadline TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0, source_scope TEXT NOT NULL, budget TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL, objective TEXT NOT NULL, checkpoint_step TEXT NOT NULL DEFAULT 'none',
  checkpoint_data TEXT NOT NULL DEFAULT '{}', terminal_reason TEXT NOT NULL DEFAULT 'none', policy_decision TEXT NOT NULL,
  started_at TEXT, finished_at TEXT, audit_ref TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_events (task_id TEXT NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (task_id, seq));
CREATE TABLE IF NOT EXISTS answers (task_id TEXT PRIMARY KEY, envelope TEXT NOT NULL);
"""


class TaskStore:
    def __init__(self, path: str | Path, key: str, rules: Rules | None = None) -> None:
        if not key:
            raise StoreKeyError("The task store is always encrypted: a key is required.")
        self._rules = rules or load_rules()
        self._lock = threading.RLock()
        self._conn = connect(path, key)
        self._conn.isolation_level = None  # explicit transactions below
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise CoreError("internal_error")  # a newer store than this code understands: refuse rather than guess
            self._conn.executescript(DDL)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._conn.close()

    # -- reading -------------------------------------------------------------------------------------------------------------------------
    def _row(self, task_id: str) -> Any:
        row = self._conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise CoreError("not_found")
        return row

    def record(self, task_id: str) -> dict[str, Any]:
        """The TaskRecord of the contract. The objective (the owner's question) is not part of it."""
        with self._lock:
            row = self._row(task_id)
        out: dict[str, Any] = {
            "task_id": row["task_id"], "state": row["state"], "created_at": row["created_at"], "updated_at": row["updated_at"],
            "deadline": row["deadline"], "attempt": row["attempt"], "cancel_requested": bool(row["cancel_requested"]),
            "source_scope": json.loads(row["source_scope"]), "budget": json.loads(row["budget"]), "idempotency_key": row["idempotency_key"],
            "checkpoint_step": row["checkpoint_step"], "terminal_reason": row["terminal_reason"], "policy_decision": json.loads(row["policy_decision"]),
        }  # fmt: skip
        validate("TaskRecord", out)
        return out

    def objective(self, task_id: str) -> str:
        with self._lock:
            return str(self._row(task_id)["objective"])

    def checkpoint(self, task_id: str) -> tuple[str, dict[str, Any]]:
        with self._lock:
            row = self._row(task_id)
            return str(row["checkpoint_step"]), json.loads(row["checkpoint_data"])

    def ids_in(self, states: tuple[str, ...]) -> list[str]:
        marks = ",".join("?" for _ in states)
        with self._lock:
            return [r["task_id"] for r in self._conn.execute(f"SELECT task_id FROM tasks WHERE state IN ({marks}) ORDER BY created_at", states)]

    # -- writing -------------------------------------------------------------------------------------------------------------------------
    def create(self, request: dict[str, Any], decision: dict[str, Any], now: datetime) -> tuple[dict[str, Any], bool]:
        """Create a task; the same idempotency key with the same request returns the existing one, with a different request it is a conflict."""
        digest = _hash_request(request)
        with self._lock:
            existing = self._conn.execute("SELECT task_id, request_hash FROM tasks WHERE idempotency_key=?", (request["idempotency_key"],)).fetchone()
            if existing is not None:
                if existing["request_hash"] != digest:
                    raise CoreError("conflict")
                return self.record(existing["task_id"]), False
            task_id = new_id()
            deadline = now + timedelta(seconds=request["budget"]["max_seconds"])
            self._conn.execute(
                "INSERT INTO tasks (task_id,state,created_at,updated_at,deadline,source_scope,budget,idempotency_key,request_hash,objective,policy_decision,audit_ref)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, "requested", _iso(now), _iso(now), _iso(deadline), json.dumps(request["source_scope"]), json.dumps(request["budget"]),
                 request["idempotency_key"], digest, request["objective"], json.dumps(decision), new_id()),
            )  # fmt: skip
            return self.record(task_id), True

    def transition(
        self, task_id: str, to: str, now: datetime, *, step: str | None = None, data: dict[str, Any] | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        """Move a task to a new state if the lifecycle allows it. Atomic: the state, checkpoint and terminal reason change together or not at all."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._apply(task_id, to, now, step, data, reason)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            return self.record(task_id)

    def _apply(self, task_id: str, to: str, now: datetime, step: str | None, data: dict[str, Any] | None, reason: str | None) -> None:
        row = self._row(task_id)
        if to not in TRANSITIONS[row["state"]]:
            raise CoreError("conflict")
        merged = {**json.loads(row["checkpoint_data"]), **(data or {})}
        attempt = row["attempt"] + (1 if to == "queued" and row["state"] in INTERRUPTED else 0)
        self._conn.execute(
            "UPDATE tasks SET state=?, updated_at=?, attempt=?, checkpoint_step=?, checkpoint_data=?, terminal_reason=?,"
            " started_at=COALESCE(started_at, ?), finished_at=? WHERE task_id=?",
            (to, _iso(now), attempt, step or row["checkpoint_step"], json.dumps(merged), reason or row["terminal_reason"],
             _iso(now) if to == "running" else None, _iso(now) if to in TERMINAL else None, task_id),
        )  # fmt: skip

    def request_cancel(self, task_id: str, now: datetime) -> dict[str, Any]:
        """Ask for cancellation: immediate if the task is not running yet, otherwise honoured at the next step boundary. Safe to repeat."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(task_id)
                if row["state"] not in TERMINAL:
                    self._conn.execute("UPDATE tasks SET cancel_requested=1, updated_at=? WHERE task_id=?", (_iso(now), task_id))
                    if row["state"] in ("requested", "policy_checked", "queued"):
                        self._apply(task_id, "cancelled", now, None, None, "cancelled")
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            return self.record(task_id)

    def expire_due(self, now: datetime) -> list[str]:
        """Expire every unfinished task whose deadline has passed."""
        expired: list[str] = []
        with self._lock:
            for task_id in self.ids_in(tuple(s for s in TRANSITIONS if s not in TERMINAL)):
                if datetime.fromisoformat(self._row(task_id)["deadline"]) < now:
                    self.transition(task_id, "expired", now, reason="expired")
                    expired.append(task_id)
        return expired

    def recover(self, now: datetime) -> list[tuple[str, str]]:
        """After a restart: an interrupted task is queued again from its last checkpoint while it has retries and time left, otherwise it ends as needs-attention."""
        done: list[tuple[str, str]] = []
        with self._lock:
            for task_id in self.ids_in(STALE_EARLY):
                self.transition(task_id, "failed", now, reason="needs_attention")
                done.append((task_id, "needs_attention"))
            for task_id in self.ids_in(INTERRUPTED):
                row = self._row(task_id)
                budget = json.loads(row["budget"])
                if row["attempt"] < budget["max_retries"] and datetime.fromisoformat(row["deadline"]) > now:
                    self.transition(task_id, "queued", now)
                    done.append((task_id, "requeued"))
                else:
                    self.transition(task_id, "failed", now, reason="needs_attention")
                    done.append((task_id, "needs_attention"))
        return done

    # -- events and answers --------------------------------------------------------------------------------------------------------------
    def append_event(self, task_id: str, event: dict[str, Any]) -> int:
        """Append a StreamEvent (it may carry content, so it lives only in this encrypted store). Returns its sequence number."""
        with self._lock:
            seq = self._conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM task_events WHERE task_id=?", (task_id,)).fetchone()[0]
            if seq > self._rules.limit("max_events_per_task"):
                return seq - 1
            full = {**event, "seq": seq, "task_id": task_id}
            validate("StreamEvent", full)
            self._conn.execute("INSERT INTO task_events (task_id, seq, payload) VALUES (?,?,?)", (task_id, seq, json.dumps(full)))
            return int(seq)

    def events_after(self, task_id: str, after: int) -> list[dict[str, Any]]:
        with self._lock:
            self._row(task_id)
            rows = self._conn.execute("SELECT payload FROM task_events WHERE task_id=? AND seq>? ORDER BY seq", (task_id, after)).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def save_answer(self, task_id: str, envelope: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO answers (task_id, envelope) VALUES (?,?)", (task_id, json.dumps(envelope)))

    def answer(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            self._row(task_id)
            row = self._conn.execute("SELECT envelope FROM answers WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise CoreError("conflict")
        return json.loads(row["envelope"])

    def receipt(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._row(task_id)
        if row["state"] not in TERMINAL:
            raise CoreError("conflict")
        out = {
            "task_id": task_id, "started_at": row["started_at"] or row["created_at"], "finished_at": row["finished_at"],
            "terminal_state": row["state"], "idempotency_key": row["idempotency_key"], "audit_ref": row["audit_ref"],
        }  # fmt: skip
        validate("ExecutionReceipt", out)
        return out
