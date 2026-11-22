"""Source designation and consent (G-O19): the durable, owner-controlled, default-deny record of which source types the owner has enabled.

This is the store BEHIND the existing `GrantSource` abstraction: `PolicyEngine` still makes every decision, and a grant minted here has the same shape (and the same identity and
ceiling binding) as any other. Nothing is enabled by default; each source type is decided on its own (documents never imply mail); there is no per-folder grant.

Lifecycle of one source type:  not_configured -> enabled | declined;  declined -> enabled;  enabled -> revoked;  revoked -> enabled (a NEW grant identity).

The store is one new encrypted file. Every change is one transaction that also appends a content-free, hash-chained audit row (source type, states, grant id, reason code: never a
folder name, content, prompt or secret). The whole record is re-verified before it is trusted: a broken chain, a changed grant, a state that disagrees with the audit, a rolled-back
tail or a store from another version makes every grant disappear (fail closed).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from kit.db import connect

from .policy import PURPOSE
from .rules import Rules, load_rules

SCHEMA_VERSION = 2
GENESIS = "0" * 64
STATES = ("enabled", "declined", "revoked")  # a source type with no row is 'not_configured'


class DesignationError(Exception):
    """A refused change. The text is a code, never content."""


class StoreCorrupt(DesignationError):
    """The record cannot be trusted. Every grant is withheld until it is repaired or replaced."""


class AnchorError(Exception):
    """The anchor refused a write that would move it backwards, fork it or overwrite an unresolved record."""


@dataclass(frozen=True)
class Intent:
    """A RESTRICTING change (a revocation) recorded in the anchor before it is committed, so that it can be completed after a crash or a snapshot restore instead of being undone."""

    source_type: str
    reason: str
    request_id: str | None = None


@dataclass(frozen=True)
class Pending:
    seq: int
    head: str
    intent: Intent | None  # None: an ordinary change (an enable or a decline), which is dropped, never replayed, if it did not commit


@dataclass(frozen=True)
class AnchorRecord:
    seq: int  # the newest (sequence, head hash) the store has durably committed AND recorded here
    head: str
    pending: Pending | None = None  # a change that was recorded as intended and is not yet recorded as committed


class RollbackAnchor(Protocol):
    """A small record kept OUTSIDE the designation database. A change is written in two phases: `prepare` records the intended (sequence, head) BEFORE the database commits, `commit`
    records it as done AFTER. So the database is never trusted beyond what the anchor has recorded, and a restored older database is detected (older than the anchor) or, if it is
    exactly one change behind an unfinished one, resolved by the recorded intent. On the Mac this is a secure-storage item (Keychain; WP3.6, NOT implemented or verified here);
    in CI it is `InMemoryAnchor`, a deterministic fake that only models the contract."""

    def read(self) -> AnchorRecord | None: ...

    def initialize(self, seq: int, head: str) -> None: ...  # first record of a new store; does nothing if a record already exists

    def prepare(
        self, seq: int, head: str, intent: Intent | None
    ) -> None: ...  # refused unless seq is ahead and nothing else is pending (or the same restriction is replayed)

    def commit(self, seq: int, head: str) -> None: ...  # the pending change becomes the committed record

    def abort(self) -> None: ...  # drop the pending record (the change did not happen)

    def reset(self) -> None: ...  # the owner starts over with a new, empty store


class RecordAnchor:
    """The anchor contract over any place that can hold ONE small record: subclasses implement `_load` and `_save` (and may fail at will), this class enforces the rules. The CI fake
    (`InMemoryAnchor`) and the Keychain anchor (`macos.KeychainAnchor`) differ only in where the record lives."""

    def __init__(self) -> None:
        self._guard = threading.RLock()  # every operation reads, decides and writes as one step

    def _load(self) -> AnchorRecord | None:
        raise NotImplementedError

    def _save(self, record: AnchorRecord | None) -> None:
        raise NotImplementedError

    def _gate(self, op: str) -> None:
        """Hook for tests and platforms to refuse an operation (raise OSError); the default allows everything."""

    def read(self) -> AnchorRecord | None:
        with self._guard:
            self._gate("read")
            return self._load()

    def initialize(self, seq: int, head: str) -> None:
        with self._guard:
            self._gate("initialize")
            if self._load() is None:
                self._save(AnchorRecord(seq, head))

    def prepare(self, seq: int, head: str, intent: Intent | None) -> None:
        with self._guard:
            self._gate("prepare")
            current = self._load()
            if current is None or seq <= current.seq:
                raise AnchorError("backwards")
            old = current.pending
            replay = old is not None and old.seq == seq and old.intent is not None and intent is not None and old.intent.source_type == intent.source_type
            if old is not None and not replay:
                raise AnchorError("pending")
            self._save(AnchorRecord(current.seq, current.head, Pending(seq, head, intent)))

    def commit(self, seq: int, head: str) -> None:
        with self._guard:
            self._gate("commit")
            current = self._load()
            if current is None or current.pending is None or (current.pending.seq, current.pending.head) != (seq, head):
                raise AnchorError("nothing to commit")
            self._save(AnchorRecord(seq, head))

    def abort(self) -> None:
        with self._guard:
            self._gate("abort")
            current = self._load()
            if current is not None:
                self._save(AnchorRecord(current.seq, current.head))

    def reset(self) -> None:
        with self._guard:
            self._gate("reset")
            self._save(None)


class InMemoryAnchor(RecordAnchor):
    """CI stand-in for the platform anchor. `fail` makes every call error; `fail_prepare` / `fail_commit` make only that write error (the platform store is unavailable)."""

    def __init__(self) -> None:
        super().__init__()
        self.record: AnchorRecord | None = None
        self.fail = False
        self.fail_prepare = False
        self.fail_commit = False

    def _load(self) -> AnchorRecord | None:
        return self.record

    def _save(self, record: AnchorRecord | None) -> None:
        self.record = record

    def _gate(self, op: str) -> None:
        if self.fail or (op == "prepare" and self.fail_prepare) or (op == "commit" and self.fail_commit):
            raise OSError("anchor unavailable")


class _Ambiguous(Exception):
    """The database is at the last committed state while the anchor holds a pending change: it either never committed, or the database was restored from before it."""

    def __init__(self, pending: Pending) -> None:
        super().__init__("pending")
        self.pending = pending


class PurgePending(DesignationError):
    """The data derived from an earlier grant has not been purged yet, so a new grant cannot be issued."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class OnboardingDecision:
    """The single Get Started decision: which source types are enabled and which are declined. A type in neither set stays not configured; enabling one never enables another."""

    enable: frozenset[str] = field(default_factory=frozenset)
    decline: frozenset[str] = field(default_factory=frozenset)
    expires_at: datetime | None = None  # optional end of the enabled grants; None means until withdrawn

    @classmethod
    def from_consent_request(cls, request: dict[str, Any]) -> OnboardingDecision:
        """From the 1.1 ConsentRequest shape ({"sources": [...]}): those types are enabled, nothing else is touched."""
        return cls(enable=frozenset(request["sources"]))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS grants (
  grant_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, max_sensitivity TEXT NOT NULL, purpose TEXT NOT NULL, issued_at TEXT NOT NULL,
  expires_at TEXT, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS state (source_type TEXT PRIMARY KEY, state TEXT NOT NULL, grant_id TEXT);
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY, at TEXT NOT NULL, source_type TEXT NOT NULL, from_state TEXT NOT NULL, to_state TEXT NOT NULL, grant_id TEXT, reason TEXT NOT NULL,
  detail TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _digest(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _grant_digest(row: Any) -> str:
    """What identifies a grant: its id, type, ceiling, purpose, issue time and expiry (never its mutable flags)."""
    return _digest(row["grant_id"], row["source_type"], row["max_sensitivity"], row["purpose"], row["issued_at"], row["expires_at"])


class DesignationStore:
    def __init__(self, path: Path, key: str | None, clock: Callable[[], datetime] = _now, rules: Rules | None = None, *, anchor: RollbackAnchor) -> None:
        self._rules, self._clock, self._anchor = rules or load_rules(), clock, anchor
        self._lock = threading.RLock()
        self._purges: dict[str, Callable[[], None]] = {}
        self.hook: Callable[[str], None] | None = None  # tests: called inside a transaction; an exception rolls it back (a simulated crash)
        self._conn = connect(path, key)
        self._conn.isolation_level = None
        with self._lock:
            fresh = self._conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0
            self._conn.executescript(_SCHEMA)
            if fresh:
                self._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
                self._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('head', ?)", (f"0:{GENESIS}",))

    def close(self) -> None:
        self._conn.close()

    # -- what can be designated -----------------------------------------------------------------------------------------------------------------
    def designable(self) -> list[str]:
        """The source types an owner may enable: known to the rules, not a restricted domain, not deferred. (Attachments, Finance and Health are never designated here.)"""
        types = self._rules.raw["source_types"]
        return sorted(t for t in types if not self._rules.is_restricted(t) and self._rules.deferred_to(t) is None)

    # -- verification: the record is trusted only while it is internally consistent ------------------------------------------------------------------------
    def _meta(self, key: str) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else ""

    def verify(self) -> None:
        """Raise StoreCorrupt unless the audit chain, the head, the states, the grants AND the external anchor all agree. A change the anchor holds as pending but the database lacks is
        resolved here: a restriction is applied (rolled forward), anything else is dropped."""
        with self._lock:
            try:
                self._checked()
            except _Ambiguous as ambiguity:
                self._resolve(ambiguity.pending)
                try:
                    self._checked()
                except _Ambiguous:
                    raise StoreCorrupt("pending_unresolved") from None

    def _checked(self) -> None:
        try:
            self._verify()
        except (StoreCorrupt, _Ambiguous):
            raise
        except Exception as error:  # an unreadable or malformed record is corrupt, whatever the cause
            raise StoreCorrupt("unreadable") from error

    def _verify(self) -> None:
        if self._meta("schema") != str(SCHEMA_VERSION):
            raise StoreCorrupt("version")
        prev = GENESIS
        derived: dict[str, tuple[str, str | None]] = {}
        revoked_ids: set[str | None] = set()
        issued: dict[str | None, str] = {}
        seen: set[str | None] = set()  # grants for which the OS permission was observed (an audited event, so it cannot be rolled back unseen)
        purged: set[str | None] = set()  # revoked grants whose derived data has been purged (an audited event, for the same reason)
        rows = self._conn.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        for number, row in enumerate(rows, 1):
            body = (row["seq"], row["at"], row["source_type"], row["from_state"], row["to_state"], row["grant_id"], row["reason"], row["detail"])
            if row["seq"] != number or row["prev_hash"] != prev or row["hash"] != _digest(prev, *body):
                raise StoreCorrupt("chain")
            self._legal(row, derived, seen, purged)
            prev = row["hash"]
            derived[row["source_type"]] = (row["to_state"], row["grant_id"])
            if row["reason"] == "owner_enabled":
                issued[row["grant_id"]] = row["detail"]
            if row["to_state"] == "revoked" and row["from_state"] == "enabled":
                revoked_ids.add(row["grant_id"])
        if self._meta("head") != f"{len(rows)}:{prev}":
            raise StoreCorrupt("head")  # rows were removed or added outside a transaction
        self._verify_anchor(rows, prev)
        self._verify_tables(derived, revoked_ids, issued)

    @staticmethod
    def _legal(row: Any, derived: dict[str, tuple[str, str | None]], seen: set[str | None], purged: set[str | None]) -> None:
        """Every audit event must be a legal step from the state the chain has reached so far (so a forged or reordered event cannot be accepted even with a valid hash)."""
        current = derived.get(row["source_type"], ("not_configured", None))
        reason, grant = row["reason"], row["grant_id"]
        if reason == "os_permission_seen":
            ok = current == ("enabled", grant) and (row["from_state"], row["to_state"]) == ("enabled", "enabled") and grant not in seen
            seen.add(grant)
        elif reason == "purge_completed":
            ok = current == ("revoked", grant) and (row["from_state"], row["to_state"]) == ("revoked", "revoked") and grant not in purged
            purged.add(grant)
        elif row["to_state"] == "enabled":
            ok = row["from_state"] == current[0] != "enabled" and (
                current[0] != "revoked" or current[1] in purged
            )  # a new grant only after the old one's data was purged
        elif row["to_state"] == "revoked":
            ok = current == ("enabled", grant) and row["from_state"] == "enabled"
        else:
            ok = row["to_state"] == "declined" and row["from_state"] == current[0] != "enabled"
        if row["from_state"] != current[0] and reason not in ("os_permission_seen", "purge_completed"):
            ok = False
        if not ok:
            raise StoreCorrupt("event")

    def _anchor_do(self, action: Callable[[], None], why: str) -> None:
        try:
            action()
        except (OSError, AnchorError) as error:
            raise StoreCorrupt(why) from error  # the store cannot be shown to match the anchor: nothing is trusted until it can

    def _verify_anchor(self, rows: list[Any], head: str) -> None:
        """The database must match the anchor EXACTLY: not older (a restored snapshot brings back matching rows, chain and head, but not the anchor outside it), and not ahead of what the
        anchor has recorded. A change the anchor holds as pending is either finalised (the database has it) or resolved (it does not)."""
        try:
            record = self._anchor.read()
        except Exception as error:  # any anchor failure means rollback cannot be ruled out: fail closed
            raise StoreCorrupt("anchor_unavailable") from error
        if record is None:
            if rows:
                raise StoreCorrupt("anchor_missing")  # a used store with no anchor cannot show it was not rolled back
            self._anchor_do(lambda: self._anchor.initialize(0, GENESIS), "anchor_unavailable")  # a new, empty store anchors its start
            return
        seq = record.seq
        if seq > len(rows) or (seq > 0 and rows[seq - 1]["hash"] != record.head) or (seq == 0 and record.head != GENESIS):
            raise StoreCorrupt("rollback")
        pending = record.pending
        if pending is None:
            if len(rows) != seq:
                raise StoreCorrupt("unanchored")  # the database holds a change the anchor never recorded
            return
        if len(rows) == pending.seq and head == pending.head:
            self._anchor_do(lambda: self._anchor.commit(pending.seq, pending.head), "anchor_unsynced")  # committed in the database: record it, or trust nothing
        elif len(rows) == seq:
            raise _Ambiguous(pending)
        else:
            raise StoreCorrupt("pending_mismatch")

    def _resolve(self, pending: Pending) -> None:
        """The anchor holds a change the database does not. An ordinary change (an enable, a decline) is dropped: nothing is granted. A RESTRICTION (withdrawal, expiry, loss of the OS
        permission) is applied now, so restoring an older snapshot, or dying before the commit, can never undo it."""
        intent = pending.intent
        if intent is None:
            self._anchor_do(self._anchor.abort, "anchor_unavailable")
            return
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            if intent.request_id is not None:
                self._conn.execute("INSERT OR IGNORE INTO requests (request_id) VALUES (?)", (intent.request_id,))
            if not self._revoke(intent.source_type, intent.reason):
                self._conn.execute("ROLLBACK")
                self._anchor_do(self._anchor.abort, "anchor_unavailable")  # nothing to restrict (the source is not enabled in this database)
                return
            seq, head = self._head()
            self._anchor_do(lambda: self._anchor.prepare(seq, head, intent), "anchor_unavailable")  # replaces the pending record for the same position
            self._conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(Exception):
                self._conn.execute("ROLLBACK")
            raise
        self._anchor_do(lambda: self._anchor.commit(seq, head), "anchor_unsynced")
        self._run_purge(intent.source_type)

    def _head(self) -> tuple[int, str]:
        count, head = self._meta("head").split(":")
        return int(count), head

    def _verify_tables(self, derived: dict[str, tuple[str, str | None]], revoked_ids: set[str | None], issued: dict[str | None, str]) -> None:
        states = {r["source_type"]: (r["state"], r["grant_id"]) for r in self._conn.execute("SELECT * FROM state")}
        if states != derived:
            raise StoreCorrupt("state")
        grants = self._conn.execute("SELECT * FROM grants").fetchall()
        if {g["grant_id"] for g in grants} != set(issued):
            raise StoreCorrupt("grants")
        for grant in grants:
            if _grant_digest(grant) != issued[grant["grant_id"]] or bool(grant["revoked"]) != (grant["grant_id"] in revoked_ids):
                raise StoreCorrupt("grant")

    def reset_anchor(self) -> None:
        """The owner deliberately starts over after losing the old database: allowed only on an EMPTY store (nothing is enabled, so nothing can be resurrected)."""
        with self._lock:
            if self._conn.execute("SELECT count(*) FROM audit").fetchone()[0] != 0:
                raise DesignationError("store_not_empty")
            self._anchor_do(self._anchor.reset, "anchor_unavailable")
            self._anchor_do(lambda: self._anchor.initialize(0, GENESIS), "anchor_unavailable")

    def health(self) -> str:
        try:
            self.verify()
        except StoreCorrupt:
            return "corrupt"
        return "ok"

    # -- writing: one transaction = the change AND its audit row ---------------------------------------------------------------------------------------
    def _audit(self, source_type: str, before: str, after: str, grant_id: str | None, reason: str, detail: str = "") -> None:
        head = self._meta("head")
        count, prev = head.split(":")
        row = (int(count) + 1, self._clock().isoformat(), source_type, before, after, grant_id, reason, detail)
        digest = _digest(prev, *row)
        self._conn.execute("INSERT INTO audit VALUES (?,?,?,?,?,?,?,?,?,?)", (*row, prev, digest))
        self._conn.execute("UPDATE meta SET value=? WHERE key='head'", (f"{row[0]}:{digest}",))

    def _transaction(self, body: Callable[[], Any], intent: Intent | None = None) -> Any:
        """One change and its audit row, in two phases with the external anchor: the anchor records the intended state BEFORE the commit and the finished state AFTER it. If the anchor
        cannot record the intent the change is not made; if it cannot record the finish, the store is not trusted (reads and writes fail closed) until it can."""
        with self._lock:
            self.verify()  # never build on a record that cannot be trusted
            before = self._head()
            self._conn.execute("BEGIN IMMEDIATE")
            prepared: tuple[int, str] | None = None
            try:
                result = body()
                after = self._head()
                if after != before:
                    self._anchor.prepare(after[0], after[1], intent)
                    prepared = after
                if self.hook is not None:
                    self.hook("before_commit")
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                if prepared is not None:
                    with contextlib.suppress(Exception):
                        self._anchor.abort()  # the change did not happen and we know it
                raise
            except BaseException:  # the process dies: the anchor's record is left for the next start to resolve (a restriction is then completed)
                with contextlib.suppress(Exception):
                    self._conn.execute("ROLLBACK")
                raise
            if self.hook is not None:
                self.hook("after_commit")
            if prepared is not None:
                with contextlib.suppress(OSError, AnchorError):
                    self._anchor.commit(*prepared)  # if this fails the store is not trusted until the next verification manages it
            return result

    def _state_of(self, source_type: str) -> tuple[str, str | None]:
        row = self._conn.execute("SELECT state, grant_id FROM state WHERE source_type=?", (source_type,)).fetchone()
        return ("not_configured", None) if row is None else (str(row["state"]), row["grant_id"])

    def _set_state(self, source_type: str, state: str, grant_id: str | None) -> None:
        self._conn.execute("INSERT OR REPLACE INTO state (source_type, state, grant_id) VALUES (?,?,?)", (source_type, state, grant_id))

    def lifecycle(self, source_type: str) -> str:
        """not_configured, enabled, declined or revoked. A corrupt record reads as not_configured: nothing is enabled."""
        try:
            with self._lock:
                self.verify()
                return self._state_of(source_type)[0]
        except StoreCorrupt:
            return "not_configured"

    def apply(self, decision: OnboardingDecision, request_id: str) -> dict[str, list[str]]:
        """Apply one Get Started decision atomically. All choices are validated first (nothing happens if any is refused). A request id is single-use: replaying it changes nothing."""
        chosen = decision.enable | decision.decline
        if decision.enable & decision.decline or not chosen or not chosen <= set(self.designable()):
            raise DesignationError("invalid_decision")
        if not 8 <= len(request_id) <= 64:  # noqa: PLR2004  (the contract's opaque identifier length)
            raise DesignationError("invalid_request_id")
        outcome: dict[str, list[str]] = {"enabled": [], "declined": [], "unchanged": []}

        def body() -> None:
            if self._conn.execute("SELECT 1 FROM requests WHERE request_id=?", (request_id,)).fetchone():
                raise DesignationError("replayed")
            self._conn.execute("INSERT INTO requests (request_id) VALUES (?)", (request_id,))
            for source_type in sorted(decision.enable):
                outcome["enabled" if self._enable(source_type, decision.expires_at) else "unchanged"].append(source_type)
            for source_type in sorted(decision.decline):
                outcome["declined" if self._decline(source_type) else "unchanged"].append(source_type)

        self._transaction(body)
        return outcome

    def _enable(self, source_type: str, expires_at: datetime | None) -> bool:
        state, _ = self._state_of(source_type)
        if state == "enabled":
            return False  # already enabled: the same grant stays (no second grant, no new identity)
        if self._purge_owed(source_type):
            raise PurgePending(source_type)
        grant_id = "g" + uuid.uuid4().hex[:24]
        ceiling = self._rules.sensitivity_of(source_type) or ""
        self._conn.execute(
            "INSERT INTO grants (grant_id, source_type, max_sensitivity, purpose, issued_at, expires_at) VALUES (?,?,?,?,?,?)",
            (grant_id, source_type, ceiling, PURPOSE, self._clock().isoformat(), None if expires_at is None else expires_at.isoformat()),
        )
        row = self._conn.execute("SELECT * FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
        self._set_state(source_type, "enabled", grant_id)
        self._audit(source_type, state, "enabled", grant_id, "owner_enabled", _grant_digest(row))
        return True

    def _decline(self, source_type: str) -> bool:
        state, grant_id = self._state_of(source_type)
        if state == "enabled":
            raise DesignationError("withdraw_instead")  # an enabled source is withdrawn, not declined
        if state in ("declined", "revoked"):
            return False
        self._set_state(source_type, "declined", None)
        self._audit(source_type, state, "declined", grant_id, "owner_declined")
        return True

    def withdraw(self, source_type: str, request_id: str) -> bool:
        """The owner withdraws access. Consuming the request id, revoking the grant, the audit row and the purge marker are ONE transaction (a crash leaves either all of it or
        none, so a failed withdrawal can be retried with the same request id); the purge runs only after that commit."""
        if not 8 <= len(request_id) <= 64:  # noqa: PLR2004
            raise DesignationError("invalid_request_id")

        def body() -> bool:
            if self._conn.execute("SELECT 1 FROM requests WHERE request_id=?", (request_id,)).fetchone():
                raise DesignationError("replayed")
            self._conn.execute("INSERT INTO requests (request_id) VALUES (?)", (request_id,))
            return self._revoke(source_type, "owner_withdrawn")

        revoked = bool(self._transaction(body, Intent(source_type, "owner_withdrawn", request_id)))
        if revoked:
            self._run_purge(source_type)
        return revoked

    def revoke(self, source_type: str, reason: str) -> bool:
        """End the enabled grant of a source type (owner withdrawal, expiry, or loss of the OS permission) and purge what was derived from it. True if something was revoked."""
        revoked = self._transaction(lambda: self._revoke(source_type, reason), Intent(source_type, reason))
        if revoked:
            self._run_purge(source_type)
        return bool(revoked)

    def _revoke(self, source_type: str, reason: str) -> bool:
        state, grant_id = self._state_of(source_type)
        if state != "enabled":
            return False
        self._conn.execute("UPDATE grants SET revoked=1 WHERE grant_id=?", (grant_id,))
        self._set_state(source_type, "revoked", grant_id)
        self._audit(source_type, "enabled", "revoked", grant_id, reason)
        return True

    def sweep(self, now: datetime | None = None) -> list[str]:
        """Revoke every enabled grant that has expired (and purge what it produced). Returns the source types affected."""
        moment = now or self._clock()
        with self._lock:
            self.verify()
            due = [
                r["source_type"]
                for r in self._conn.execute("SELECT source_type, expires_at FROM grants WHERE revoked=0 AND expires_at IS NOT NULL")
                if datetime.fromisoformat(r["expires_at"]) <= moment
            ]
        return [t for t in sorted(due) if self.revoke(t, "grant_expired")]

    # -- the OS permission seen at least once (so a later loss is a revocation, not a first-run state): an AUDITED, anchored event, never a loose flag -------------------
    def note_os_granted(self, source_type: str) -> None:
        """Record, once per grant, that the platform permission was positively observed. It goes through the same anchored transaction as every other change, so restoring an
        older database cannot silently forget it."""
        with self._lock:
            if not self.os_was_granted(source_type):
                self._transaction(lambda: self._record_os_seen(source_type))

    def _record_os_seen(self, source_type: str) -> None:
        state, grant_id = self._state_of(source_type)
        if state == "enabled":
            self._audit(source_type, "enabled", "enabled", grant_id, "os_permission_seen")

    def os_was_granted(self, source_type: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM audit a JOIN state s ON a.source_type=s.source_type AND a.grant_id=s.grant_id "
                "WHERE a.reason='os_permission_seen' AND s.state='enabled' AND a.source_type=?",
                (source_type,),
            ).fetchone()
        return row is not None

    # -- purging what a revoked grant produced: completion is an AUDITED, anchored event too ------------------------------------------------------------------------
    def register_purge(self, source_type: str, purge: Callable[[], None]) -> None:
        """The function that deletes everything derived from a source type (its index, caches). Called after a revocation commits."""
        self._purges[source_type] = purge

    _OWED = (
        "SELECT g.source_type, g.grant_id FROM grants g WHERE g.revoked=1 AND NOT EXISTS "
        "(SELECT 1 FROM audit a WHERE a.reason='purge_completed' AND a.grant_id=g.grant_id)"
    )

    def _purge_owed(self, source_type: str) -> bool:
        return any(r["source_type"] == source_type for r in self._conn.execute(self._OWED))

    def _run_purge(self, source_type: str) -> None:
        purge = self._purges.get(source_type)
        if purge is None:
            return  # stays owed, and a new grant for this type is refused until it has run and been recorded
        try:
            purge()
        except Exception:  # noqa: BLE001  (whatever the purge raised, the source stays revoked and the purge stays owed; it is retried by run_pending_purges)
            return
        with contextlib.suppress(DesignationError, OSError, AnchorError):
            self._transaction(lambda: self._record_purged(source_type))  # not recorded (anchor or store unavailable): it stays owed and is simply run again

    def _record_purged(self, source_type: str) -> None:
        for row in self._conn.execute(self._OWED).fetchall():
            if row["source_type"] == source_type:
                self._audit(source_type, "revoked", "revoked", row["grant_id"], "purge_completed")

    def pending_purges(self) -> list[str]:
        """Source types whose revoked grant has no recorded purge completion (derived from the audited chain, so an older snapshot cannot show a purge as done)."""
        with self._lock:
            try:
                self.verify()
            except StoreCorrupt:
                return []
            return sorted({r["source_type"] for r in self._conn.execute(self._OWED)})

    def run_pending_purges(self) -> list[str]:
        """Run at start-up: finish any purge a crash or a failure left owed. Returns the source types still owed afterwards."""
        for source_type in self.pending_purges():
            self._run_purge(source_type)
        return self.pending_purges()

    # -- reading: the GrantSource the policy engine consumes ------------------------------------------------------------------------------------------------------
    def grants_for(self, source_type: str) -> list[dict[str, Any]]:
        """SourceGrant records (history included, revoked ones flagged) in the shape PolicyEngine already reads. A record that cannot be verified yields NO grant."""
        with self._lock:
            try:
                self.verify()
            except StoreCorrupt:
                return []
            rows = self._conn.execute("SELECT * FROM grants WHERE source_type=? ORDER BY rowid", (source_type,)).fetchall()
        return [self._as_grant(r) for r in rows]

    @staticmethod
    def _as_grant(row: Any) -> dict[str, Any]:
        return {
            "grant_id": row["grant_id"],
            "source_type": row["source_type"],
            "max_sensitivity": row["max_sensitivity"],
            "designated_by": "owner",
            "purpose": row["purpose"],
            "issued_at": row["issued_at"],
            "expires_at": row["expires_at"],
            "revoked": bool(row["revoked"]),
        }

    def audit_log(self) -> list[dict[str, Any]]:
        """The content-free audit trail (types, states, grant ids and reason codes only)."""
        with self._lock:
            self.verify()
            rows = self._conn.execute("SELECT seq, at, source_type, from_state, to_state, grant_id, reason FROM audit ORDER BY seq").fetchall()
        return [dict(r) for r in rows]

    def latest_grants(self, source_types: Iterable[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for source_type in source_types:
            grants = self.grants_for(source_type)
            if grants:
                out.append(grants[-1])
        return out
