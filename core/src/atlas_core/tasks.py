"""Durable task state in a NEW, separate, additive, encrypted store (its own file, its own key). It never touches an existing database or key;
deleting the file rolls the whole thing back.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import secrets
import shlex
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from kit.db import EncryptionError, connect

from .contracts import validate
from .errors import CoreError, user_error
from .events import new_id
from .rules import Rules, load_rules

SCHEMA_VERSION = 1
KEY_ENV, KEY_FILE_ENV = "ATLAS_TASK_KEY", "ATLAS_TASK_KEY_FILE"
KEYCHAIN_ITEM = "atlas-task-key"  # the dedicated Keychain item that supplies the key on the Mac (provisioning script: not part of this stage)
STEPS = ("none", "policy_checked", "retrieved", "drafted", "verified")
TERMINAL = frozenset({"completed", "partially_completed", "failed", "cancelled", "expired"})
CLOSING_EVENTS = frozenset({"final", "error"})  # the stream event that closes a task: its answer, or its user-safe error
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


SOURCE_ENV = "ATLAS_TASK_KEY_SOURCE"  # "env" or "file": an explicit opt-in to the development providers on a Mac
SECURITY_TOOL = "security"  # macOS command-line access to the Keychain (the same tool the existing scripts use)
KEYCHAIN_NOT_FOUND = 44  # exit status of `security find-generic-password` when the item does not exist
KEY_BYTES = 32


class KeyProvider(Protocol):
    def get(self) -> str: ...


class EnvKeyProvider:
    """DEVELOPMENT/TEST provider: the key from ATLAS_TASK_KEY_FILE or ATLAS_TASK_KEY. Never the Mac production path (see default_provider)."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._env = os.environ if environ is None else environ

    def get(self) -> str:
        path = self._env.get(KEY_FILE_ENV)
        key = Path(path).read_text().strip() if path else self._env.get(KEY_ENV, "")
        if not key:
            raise StoreKeyError(f"No key for the task store ({KEY_ENV} or {KEY_FILE_ENV}).")
        return key


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class KeychainKeyProvider:
    """The Mac production provider: the key lives in the dedicated Keychain item `atlas-task-key` (never in a file or an environment variable).

    `get` reads it; `provision` creates a random 256-bit key if the item does not exist (the key is passed to `security -i` on standard input, never on a command line).
    The runner is injectable so the commands can be tested on Linux; the real `security` tool is NOT VERIFIED until it runs on a Mac.
    """

    def __init__(self, account: str | None = None, runner: Runner = subprocess.run) -> None:
        self._account = account or getpass.getuser()
        self._run = runner

    def get(self) -> str:
        done = self._run([SECURITY_TOOL, "find-generic-password", "-a", self._account, "-s", KEYCHAIN_ITEM, "-w"], capture_output=True, text=True, check=False)
        if done.returncode == KEYCHAIN_NOT_FOUND:
            raise StoreKeyError("The task store key has not been provisioned in the Keychain.")
        if done.returncode != 0 or not done.stdout.strip():
            raise StoreKeyError("The task store key could not be read from the Keychain.")
        return str(done.stdout.strip())

    def provision(self) -> bool:
        """Create the Keychain item with a fresh random key unless it exists. Returns True if it was created."""
        try:
            self.get()
        except StoreKeyError:
            pass
        else:
            return False
        key = secrets.token_hex(KEY_BYTES)
        command = f"add-generic-password -a {shlex.quote(self._account)} -s {KEYCHAIN_ITEM} -w {key}\n"
        done = self._run([SECURITY_TOOL, "-i"], input=command, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise StoreKeyError("The task store key could not be stored in the Keychain.")
        return True


def default_provider(platform: str | None = None, environ: Mapping[str, str] | None = None) -> KeyProvider:
    """On macOS the Keychain provider, always, unless the owner opts in to the development providers with ATLAS_TASK_KEY_SOURCE=env|file (a plaintext key file or an environment
    variable never becomes the Mac production path silently). On other platforms (Linux CI, tests) the environment provider."""
    env = os.environ if environ is None else environ
    if (platform or sys.platform) == "darwin" and env.get(SOURCE_ENV) not in ("env", "file"):
        return KeychainKeyProvider()
    return EnvKeyProvider(env)


def task_store_key(provider: KeyProvider | None = None) -> str:
    """The task store's own key from its provider (never shared with any other database)."""
    return (provider or default_provider()).get()


def open_task_store(path: str | Path, provider: KeyProvider | None = None) -> TaskStore:
    return TaskStore(path, task_store_key(provider))


def _state(state: str) -> dict[str, Any]:
    return {"type": "state", "state": state}


def _error(code: str, task_id: str) -> dict[str, Any]:
    return {"type": "error", "error": user_error(code, task_id)}


def scrub(data: dict[str, Any], only: str | None = None) -> dict[str, Any]:
    """The checkpoint without derived source content: passage text, the draft and the quotes of citations are dropped; the content-free evidence (source id, version, locator, span)
    stays, because later checks need to know WHICH sources a task used. With `only`, just the passages and citations of that source type."""
    out = dict(data)
    if only is None:
        out.pop("draft", None)
    passages = [{"evidence": p["evidence"]} if only is None or p["evidence"]["source_type"] == only else p for p in out.get("passages", [])]
    if "passages" in out:
        out["passages"] = passages
    if "citations" in out:
        out["citations"] = [{"evidence": c["evidence"]} if only is None or c["evidence"]["source_type"] == only else c for c in out["citations"]]
    return out


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
        self.hook: Callable[[str], None] | None = (
            None  # tests: called inside a transition's transaction ('after_state', 'after_events'); an exception rolls everything back
        )
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

    def _fire(self, name: str) -> None:
        if self.hook is not None:
            self.hook(name)

    def _append_in_txn(self, task_id: str, event: dict[str, Any]) -> None:
        """Append a StreamEvent inside the caller's open transaction (so it commits or rolls back with the state change it describes)."""
        seq = self._conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM task_events WHERE task_id=?", (task_id,)).fetchone()[0]
        if seq > self._rules.limit("max_events_per_task"):
            return
        full = {**event, "seq": seq, "task_id": task_id}
        validate("StreamEvent", full)
        self._conn.execute("INSERT INTO task_events (task_id, seq, payload) VALUES (?,?,?)", (task_id, seq, json.dumps(full)))

    def transition(  # noqa: PLR0913  (everything that describes one change is committed together, so it is passed together)
        self,
        task_id: str,
        to: str,
        now: datetime,
        *,
        step: str | None = None,
        data: dict[str, Any] | None = None,
        reason: str | None = None,
        events: Sequence[dict[str, Any]] = (),
        answer: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Move a task to a new state if the lifecycle allows it. Atomic: the state, checkpoint, terminal reason, the stream events that describe the change AND (when given) the
        answer envelope commit together or not at all, so a crash can never leave a finished task without its closing event, or an answer without its state."""
        if to in TERMINAL and sorted(e.get("type", "") for e in events if e.get("type") in CLOSING_EVENTS) not in (["error"], ["final"]):
            raise CoreError("conflict")  # a terminal state is only ever committed together with exactly one closing event (final or error)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._apply(task_id, to, now, step, data, reason)
                if answer is not None:
                    self._conn.execute("INSERT OR REPLACE INTO answers (task_id, envelope) VALUES (?,?)", (task_id, json.dumps(answer)))
                self._fire("after_state")
                for event in events:
                    self._append_in_txn(task_id, event)
                self._fire("after_events")
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
        if to in TERMINAL:
            merged = scrub(merged)  # a finished task keeps no passage text, draft or quote: the saved answer is the only copy of what was said
        attempt = row["attempt"] + (1 if to == "queued" and row["state"] in INTERRUPTED else 0)
        self._conn.execute(
            "UPDATE tasks SET state=?, updated_at=?, attempt=?, checkpoint_step=?, checkpoint_data=?, terminal_reason=?,"
            " started_at=COALESCE(started_at, ?), finished_at=? WHERE task_id=?",
            (to, _iso(now), attempt, step or row["checkpoint_step"], json.dumps(merged), reason or row["terminal_reason"],
             _iso(now) if to == "running" else None, _iso(now) if to in TERMINAL else None, task_id),
        )  # fmt: skip

    def purge_type(self, source_type: str, replacement: Callable[[str, frozenset[str]], dict[str, Any]]) -> int:
        """Everything a task holds that came from `source_type` is removed (passage text, quotes, the draft), the saved answer of a finished task that used it is replaced by
        `replacement(task_id, used types)` (a content-free withheld answer) and its closing `final` event by the fixed `source_denied` error. Idempotent; returns how many tasks changed."""
        changed = 0
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for row in self._conn.execute("SELECT task_id, state, checkpoint_data FROM tasks").fetchall():
                    data = json.loads(row["checkpoint_data"])
                    used = frozenset(p["evidence"]["source_type"] for p in data.get("passages", []))
                    envelope = self._conn.execute("SELECT envelope FROM answers WHERE task_id=?", (row["task_id"],)).fetchone()
                    cited = frozenset(c["evidence"]["source_type"] for c in json.loads(envelope["envelope"])["citations"]) if envelope else frozenset()
                    if source_type not in used | cited:
                        continue
                    changed += 1
                    self._conn.execute("UPDATE tasks SET checkpoint_data=? WHERE task_id=?", (json.dumps(scrub(data, source_type)), row["task_id"]))
                    if envelope is not None and row["state"] in TERMINAL:
                        self._conn.execute(
                            "UPDATE answers SET envelope=? WHERE task_id=?", (json.dumps(replacement(row["task_id"], used | cited)), row["task_id"])
                        )
                    for event in self._conn.execute("SELECT seq, payload FROM task_events WHERE task_id=?", (row["task_id"],)).fetchall():
                        if json.loads(event["payload"]).get("type") == "final":
                            error = {**_error("source_denied", row["task_id"]), "seq": event["seq"], "task_id": row["task_id"]}
                            self._conn.execute("UPDATE task_events SET payload=? WHERE task_id=? AND seq=?", (json.dumps(error), row["task_id"], event["seq"]))
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return changed

    def note(self, task_id: str, data: dict[str, Any], now: datetime) -> None:
        """Durably record a fact about the task's progress without changing its state (for example 'retrieval is about to start')."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(task_id)
                merged = {**json.loads(row["checkpoint_data"]), **data}
                self._conn.execute("UPDATE tasks SET checkpoint_data=?, updated_at=? WHERE task_id=?", (json.dumps(merged), _iso(now), task_id))
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

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
                        self._fire("after_state")
                        self._append_in_txn(task_id, {"type": "state", "state": "cancelled"})
                        self._append_in_txn(task_id, _error("task_cancelled", task_id))
                        self._fire("after_events")
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
                    self.transition(task_id, "expired", now, reason="expired", events=[_state("expired"), _error("task_expired", task_id)])
                    expired.append(task_id)
        return expired

    def recover(self, now: datetime) -> list[tuple[str, str]]:
        """After a restart: an interrupted task is queued again from its last checkpoint while it has retries and time left, otherwise it ends as needs-attention."""
        done: list[tuple[str, str]] = []
        with self._lock:
            for task_id in self.ids_in(STALE_EARLY):
                self.transition(task_id, "failed", now, reason="needs_attention", events=[_state("failed"), _error("needs_attention", task_id)])
                done.append((task_id, "needs_attention"))
            for task_id in self.ids_in(INTERRUPTED):
                row = self._row(task_id)
                budget = json.loads(row["budget"])
                if row["attempt"] < budget["max_retries"] and datetime.fromisoformat(row["deadline"]) > now:
                    self.transition(task_id, "queued", now, events=[_state("queued")])
                    done.append((task_id, "requeued"))
                else:
                    self.transition(task_id, "failed", now, reason="needs_attention", events=[_state("failed"), _error("needs_attention", task_id)])
                    done.append((task_id, "needs_attention"))
        return done

    # -- events and answers --------------------------------------------------------------------------------------------------------------
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
