"""Source designation and consent (G-O19): the durable, owner-controlled, default-deny record of which source types the owner has enabled.

This is the store BEHIND the existing `GrantSource` abstraction: `PolicyEngine` still makes every decision, and a grant minted here has the same shape (and the same identity and
ceiling binding) as any other. Nothing is enabled by default; each source type is decided on its own (documents never imply mail); there is no per-folder grant.

Lifecycle of one source type:  not_configured -> enabled | declined;  declined -> enabled;  enabled -> revoked;  revoked -> enabled (a NEW grant identity).

The store is one new encrypted file. Every change is one transaction that also appends a content-free, hash-chained audit row (source type, states, grant id, reason code: never a
folder name, content, prompt or secret). The whole record is re-verified before it is trusted: a broken chain, a changed grant, a state that disagrees with the audit, a rolled-back
tail or a store from another version makes every grant disappear (fail closed).
"""

from __future__ import annotations

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

SCHEMA_VERSION = 1
GENESIS = "0" * 64
STATES = ("enabled", "declined", "revoked")  # a source type with no row is 'not_configured'


class DesignationError(Exception):
    """A refused change. The text is a code, never content."""


class StoreCorrupt(DesignationError):
    """The record cannot be trusted. Every grant is withheld until it is repaired or replaced."""


class AnchorError(Exception):
    """The anchor refused a write that would move it backwards or fork it."""


class RollbackAnchor(Protocol):
    """A tiny monotonic record kept OUTSIDE the designation database: the newest (sequence, head hash) the store has committed. Restoring an older copy of the whole database
    cannot also restore it, so a database older than the anchor is a rollback and is refused. On the Mac this is a secure-storage item (Keychain; WP3.6, NOT implemented or
    verified here); in CI it is `InMemoryAnchor`, a deterministic fake that only models the contract."""

    def read(self) -> tuple[int, str] | None: ...

    def advance(self, seq: int, head: str) -> None: ...  # monotonic: never backwards, never a different head for the same sequence

    def reset(self) -> None: ...  # the owner starts over with a new, empty store


class InMemoryAnchor:
    """CI stand-in for the platform anchor. `fail` makes every call error; `fail_advance` makes only writes error (the platform store is unavailable)."""

    def __init__(self) -> None:
        self.value: tuple[int, str] | None = None
        self.fail = False
        self.fail_advance = False

    def read(self) -> tuple[int, str] | None:
        if self.fail:
            raise OSError("anchor unavailable")
        return self.value

    def advance(self, seq: int, head: str) -> None:
        if self.fail or self.fail_advance:
            raise OSError("anchor unavailable")
        if self.value is not None and (seq < self.value[0] or (seq == self.value[0] and head != self.value[1])):
            raise AnchorError("backwards")
        self.value = (seq, head)

    def reset(self) -> None:
        if self.fail:
            raise OSError("anchor unavailable")
        self.value = None


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
  expires_at TEXT, revoked INTEGER NOT NULL DEFAULT 0, revoke_reason TEXT, os_seen INTEGER NOT NULL DEFAULT 0, purge_pending INTEGER NOT NULL DEFAULT 0);
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
                self._pin(0, GENESIS)  # a brand-new store anchors its start (an existing anchor is left alone: see _verify_anchor)

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
        """Raise StoreCorrupt unless the audit chain, the head, the states and the grants all agree."""
        with self._lock:
            try:
                self._verify()
            except StoreCorrupt:
                raise
            except Exception as error:  # an unreadable or malformed record is corrupt, whatever the cause
                raise StoreCorrupt("unreadable") from error

    def _verify(self) -> None:
        if self._meta("schema") != str(SCHEMA_VERSION):
            raise StoreCorrupt("version")
        prev, derived, revoked_ids, issued = GENESIS, {}, set(), {}
        rows = self._conn.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        for number, row in enumerate(rows, 1):
            body = (row["seq"], row["at"], row["source_type"], row["from_state"], row["to_state"], row["grant_id"], row["reason"], row["detail"])
            if row["seq"] != number or row["prev_hash"] != prev or row["hash"] != _digest(prev, *body):
                raise StoreCorrupt("chain")
            prev = row["hash"]
            derived[row["source_type"]] = (row["to_state"], row["grant_id"])
            if row["to_state"] == "enabled":
                issued[row["grant_id"]] = row["detail"]
            if row["to_state"] == "revoked":
                revoked_ids.add(row["grant_id"])
        if self._meta("head") != f"{len(rows)}:{prev}":
            raise StoreCorrupt("head")  # rows were removed or added outside a transaction
        self._verify_anchor(rows, prev)
        self._verify_tables(derived, revoked_ids, issued)

    def _pin(self, seq: int, head: str) -> None:
        """Move the external anchor forward. A failure is tolerated: the database is then ahead of the anchor, which the next verification catches up (never behind)."""
        try:
            self._anchor.advance(seq, head)
        except (OSError, AnchorError):
            return

    def _verify_anchor(self, rows: list[Any], head: str) -> None:
        """The database must not be OLDER than the anchor. A whole-database restore brings back matching rows, chain and head, but not the anchor outside it."""
        try:
            pinned = self._anchor.read()
        except Exception as error:  # any anchor failure means rollback cannot be ruled out: fail closed
            raise StoreCorrupt("anchor_unavailable") from error
        if pinned is None:
            if rows:
                raise StoreCorrupt("anchor_missing")  # a used store with no anchor cannot show it was not rolled back
            return
        seq, anchored = pinned
        if seq > len(rows) or (seq > 0 and rows[seq - 1]["hash"] != anchored) or (seq == 0 and anchored != GENESIS):
            raise StoreCorrupt("rollback")
        if len(rows) > seq:
            self._pin(len(rows), head)  # the database is ahead (a crash between a commit and the anchor write): catch the anchor up

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
            self._anchor.reset()
            self._pin(0, GENESIS)

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

    def _transaction(self, body: Callable[[], Any]) -> Any:
        with self._lock:
            self.verify()  # never build on a record that cannot be trusted
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                result = body()
                if self.hook is not None:
                    self.hook("before_commit")
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            if self.hook is not None:
                self.hook("after_commit")  # tests: a crash here leaves the database ahead of the anchor
            count, head = self._meta("head").split(":")
            self._pin(int(count), head)
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
        if self._conn.execute("SELECT 1 FROM grants WHERE source_type=? AND purge_pending=1", (source_type,)).fetchone():
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

        revoked = bool(self._transaction(body))
        if revoked:
            self._run_purge(source_type)
        return revoked

    def revoke(self, source_type: str, reason: str) -> bool:
        """End the enabled grant of a source type (owner withdrawal, expiry, or loss of the OS permission) and purge what was derived from it. True if something was revoked."""
        revoked = self._transaction(lambda: self._revoke(source_type, reason))
        if revoked:
            self._run_purge(source_type)
        return bool(revoked)

    def _revoke(self, source_type: str, reason: str) -> bool:
        state, grant_id = self._state_of(source_type)
        if state != "enabled":
            return False
        self._conn.execute("UPDATE grants SET revoked=1, revoke_reason=?, purge_pending=1 WHERE grant_id=?", (reason, grant_id))
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

    # -- the OS permission seen at least once (so a later loss is a revocation, not a first-run state) ------------------------------------------------------
    def note_os_granted(self, source_type: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE grants SET os_seen=1 WHERE source_type=? AND revoked=0", (source_type,))

    def os_was_granted(self, source_type: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM grants WHERE source_type=? AND revoked=0 AND os_seen=1", (source_type,)).fetchone()
        return row is not None

    # -- purging what a revoked grant produced -------------------------------------------------------------------------------------------------------------
    def register_purge(self, source_type: str, purge: Callable[[], None]) -> None:
        """The function that deletes everything derived from a source type (its index, caches). Called after a revocation commits."""
        self._purges[source_type] = purge

    def _run_purge(self, source_type: str) -> None:
        purge = self._purges.get(source_type)
        if purge is None:
            return  # stays pending, and a new grant for this type is refused until it has run
        try:
            purge()
        except Exception:  # noqa: BLE001  (whatever the purge raised, the source stays revoked and the purge stays pending) a failed purge leaves the source revoked and the purge pending; it is retried by run_pending_purges
            return
        with self._lock:
            self._conn.execute("UPDATE grants SET purge_pending=0 WHERE source_type=?", (source_type,))

    def pending_purges(self) -> list[str]:
        with self._lock:
            return sorted({r["source_type"] for r in self._conn.execute("SELECT source_type FROM grants WHERE purge_pending=1")})

    def run_pending_purges(self) -> list[str]:
        """Run at start-up: finish any purge a crash or a failure left pending. Returns the source types still pending afterwards."""
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
