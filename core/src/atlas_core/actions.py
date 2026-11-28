"""The Action Gateway (Stage 6; PRD 4.4): the only door through which Atlas does anything with a consequence.

* **The approval list is closed.** An action needs the owner's approval only if one of its declared effects is on PRD 4.4's four categories: (1) sending, publishing, sharing or uploading outside the Mac,
  (2) spending money, (3) deleting or overwriting without a reliable undo, (4) unlocking physical access or disabling a safety/security system. Nothing else ever prompts: `prompts` counts the approvals
  asked for, and a reversible local action leaves it at zero.
* **Approval is single-use and bound.** It is bound to a hash of the action name and its whole payload (destination, recipient, attachments, amount, terms are part of the payload), expires, and is consumed
  by the one execution it was for. Any material change to the payload is a different binding, so it needs a new approval.
* **Content is never the owner.** A proposal whose origin is untrusted content (a document, an e-mail, a web page, a tool's output) is refused outright: it cannot be approved by what it says, and it cannot
  widen anything. Only an owner request or the owner's own automation policy may propose.
* **Honest outcomes.** Every proposal ends as `done`, `needs_approval`, `refused` or `failed`, with a code. A reversible action records how to undo it; a retried proposal with the same idempotency key
  returns the recorded result and does not run twice; the same key with a different payload is a conflict.
* **Audit.** Every outcome is appended to a hash-chained log of the action name, a hash of the payload, the outcome and the approval used; never the payload itself.
* **Revocable connectors.** An action may belong to a connector; revoking the connector refuses all its actions from then on.

This module performs no I/O of its own: handlers are injected, so a test (or an adapter) supplies the effect.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

EFFECTS = frozenset({"read", "local_reversible", "local_irreversible", "external_send", "spend", "physical_security"})
CATEGORY = {
    "external_send": 1,
    "spend": 2,
    "local_irreversible": 3,
    "physical_security": 4,
}  # PRD 4.4, exhaustive: a new category is an owner decision, not a code change here
ORIGINS = frozenset({"owner_request", "owner_policy", "untrusted_content"})
APPROVAL_TTL = timedelta(minutes=10)
GENESIS = "0" * 64

Handler = Callable[[dict[str, Any]], dict[str, Any]]
Undo = Callable[[dict[str, Any], dict[str, Any]], None]


class ActionNotPerformed(Exception):
    """Raised by a handler that can PROVE it did nothing (it refused before any effect). Only this makes a failed external action safe to retry under the same idempotency key; any other failure of an
    action with an external connector is an ambiguous outcome: the provider may have committed it, so it is never run again blindly (TARGET_ARCHITECTURE §20)."""


@dataclass(frozen=True)
class ActionSpec:
    name: str
    effects: frozenset[str]
    handler: Handler
    undo: Undo | None = None
    connector: str | None = None
    # an undo that also marks its durable receipt undone in the same transaction as the effect (UC-L14); used whenever receipts are kept
    atomic_undo: Callable[[dict[str, Any], dict[str, Any], str], None] | None = None

    def __post_init__(self) -> None:
        if not self.effects or not self.effects <= EFFECTS:
            raise ValueError("effects must be a non-empty subset of the closed list")
        if "local_reversible" in self.effects and self.undo is None:
            raise ValueError("an action that claims to be reversible must say how to undo it")

    @property
    def category(self) -> int | None:
        """The approval category it falls under, or None if it never prompts."""
        found = [CATEGORY[e] for e in self.effects if e in CATEGORY]
        return min(found) if found else None


@dataclass(frozen=True)
class Outcome:
    status: str  # done | needs_approval | refused | failed
    code: str = ""
    action_id: str | None = None
    result: dict[str, Any] | None = None
    approval_id: str | None = None
    category: int | None = None
    exact_payload: dict[str, Any] | None = None  # what the owner is shown for approval, exactly as it will run


@dataclass
class Approval:
    approval_id: str
    binding: str
    category: int
    expires_at: datetime
    granted: bool = False
    used: bool = False


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    at: str
    action: str
    outcome: str
    code: str
    payload_hash: str
    approval_id: str | None
    prev: str
    digest: str


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def anchored(history: list[AuditEntry], anchor: tuple[int, str] | None) -> bool:
    """Whether a loaded audit history still holds the entry its external anchor names (same sequence, same digest). An anchor beyond the history
    means the file was deleted or truncated; a history one entry past the anchor is an append whose anchor update was interrupted, and is fine."""
    if anchor is None:
        return True  # no anchor yet: a first run, or an installation from before the anchor existed (anchored from its next entry on)
    seq, digest = anchor
    return 0 < seq <= len(history) and history[seq - 1].seq == seq and history[seq - 1].digest == digest


def binding_of(name: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(name.encode() + b"\n" + _canonical(payload)).hexdigest()


class AuditFile:
    """The audit chain on disk: one JSON line per entry, appended and flushed before the outcome is returned, readable only by the owner (mode 0600). `load` returns None for a file whose chain does not verify
    (a missing, reordered, edited or truncated line): the caller must then refuse to run actions rather than continue a history it cannot vouch for."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, entry: AuditEntry) -> None:
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def load(self) -> list[AuditEntry] | None:
        if not self._path.exists():
            return []
        try:
            entries = [AuditEntry(**json.loads(line)) for line in self._path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (ValueError, TypeError):
            return None
        return entries if _chain_ok(entries) else None


def _digest_of(prev: str, e: AuditEntry) -> str:
    return hashlib.sha256("|".join((prev, str(e.seq), e.at, e.action, e.outcome, e.code, e.payload_hash, e.approval_id or "")).encode()).hexdigest()


def _chain_ok(entries: list[AuditEntry]) -> bool:
    prev = GENESIS
    for position, e in enumerate(entries, start=1):
        if e.seq != position or e.prev != prev or e.digest != _digest_of(prev, e):
            return False
        prev = e.digest
    return True


@dataclass
class _Done:
    spec: ActionSpec
    payload: dict[str, Any]
    result: dict[str, Any]
    undone: bool = False


class IdempotencyFile:
    """What the gateway has already decided, kept across a restart: one JSON line per (action, idempotency key) with the payload HASH, the outcome status and code and the action id. Never the payload or the
    result (those can hold personal content), so a replay after a restart answers `done` or `outcome_unknown` without running anything again. Owner-only (0600), appended and fsynced before the outcome returns."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, name: str, key: str, digest: str, outcome: Outcome) -> None:
        row = {"name": name, "key": key, "digest": digest, "status": outcome.status, "code": outcome.code, "action_id": outcome.action_id}
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def load(self) -> dict[tuple[str, str], tuple[str, Outcome]]:
        seen: dict[tuple[str, str], tuple[str, Outcome]] = {}
        if not self._path.exists():
            return seen
        for line in self._path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if row["status"] == "forgotten":  # an intent whose handler proved it did nothing: the key may be tried again
                    seen.pop((row["name"], row["key"]), None)
                    continue
                seen[(row["name"], row["key"])] = (row["digest"], Outcome(row["status"], row.get("code", ""), row.get("action_id")))
            except (ValueError, KeyError, TypeError):
                continue  # a torn last line is skipped; every complete line before it still counts
        return seen


class ApprovalFile:
    """Pending and granted approvals, kept across a restart (ATLAS-ACT-019): one JSON line per change with the approval id, the binding HASH, the
    category, the expiry and whether it was granted or used. Never the payload. Owner-only (0600), appended and fsynced: `used` is on disk before
    the approved action runs, so a restart can never let one approval run twice. The last line for an id wins; a torn last line is cut off
    before the next append and ignored on replay; any other bad line makes the state untrusted."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, approval: Approval) -> None:
        row = {
            "id": approval.approval_id,
            "binding": approval.binding,
            "category": approval.category,
            "expires_at": approval.expires_at.isoformat(),
            "granted": approval.granted,
            "used": approval.used,
        }
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "r+b") as handle:  # framed: a torn last line is cut off first, so this record starts on its own line
            data = handle.read()
            if data and not data.endswith(b"\n"):
                handle.truncate(data.rfind(b"\n") + 1)
            handle.seek(0, os.SEEK_END)
            handle.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())

    def load(self) -> dict[str, Approval]:
        """Strict replay: every complete line must be a valid record (otherwise ValueError, and the Core serves no actions); only a torn last line,
        one without its newline, is ignored as the interrupted write it is."""
        found: dict[str, Approval] = {}
        if not self._path.exists():
            return found
        data = self._path.read_bytes()
        complete = data if data.endswith(b"\n") else data[: data.rfind(b"\n") + 1]
        for line in complete.decode("utf-8").splitlines():
            try:
                approval = _strict_approval(json.loads(line))
            except (ValueError, KeyError, TypeError):
                raise ValueError("approval_state_corrupt") from None
            before = found.get(approval.approval_id)
            if before is not None and not _allowed_transition(before, approval):
                raise ValueError("approval_state_corrupt")  # a record that changes what was approved, or un-grants or un-uses it
            found[approval.approval_id] = approval
        return found


_HEX16, _HEX64 = re.compile(r"[0-9a-f]{16}"), re.compile(r"[0-9a-f]{64}")


def _strict_approval(row: Any) -> Approval:
    """One journal record, taken only if every field has exactly its own type and form: nothing is coerced (a string "false" is not False)."""
    if not isinstance(row, dict) or set(row) != {"id", "binding", "category", "expires_at", "granted", "used"}:
        raise ValueError("fields")
    approval_id, binding, category, expires, granted, used = (row[k] for k in ("id", "binding", "category", "expires_at", "granted", "used"))
    if not (isinstance(approval_id, str) and _HEX16.fullmatch(approval_id) and isinstance(binding, str) and _HEX64.fullmatch(binding)):
        raise ValueError("identity")
    if type(category) is not int or category not in CATEGORY.values() or type(granted) is not bool or type(used) is not bool:
        raise ValueError("types")
    at = datetime.fromisoformat(expires) if isinstance(expires, str) else None
    if at is None or at.utcoffset() is None or (used and not granted):
        raise ValueError("expiry_or_state")
    return Approval(approval_id, binding, category, at, granted, used)


def _allowed_transition(before: Approval, after: Approval) -> bool:
    """A later record for the same approval may only move it forward (pending, granted, used) and never change what it binds."""
    same = (before.binding, before.category, before.expires_at) == (after.binding, after.category, after.expires_at)
    return same and (after.granted or not before.granted) and (after.used or not before.used)


class ReceiptBook(Protocol):
    """Durable, encrypted action receipts: what an executed action's undo needs (its name, payload and result), so undo works after a restart."""

    def put_receipt(self, action_id: str, name: str, payload: dict[str, Any], result: dict[str, Any]) -> None: ...
    def receipt(self, action_id: str) -> tuple[str, dict[str, Any], dict[str, Any], bool] | None: ...
    def mark_undone(self, action_id: str) -> None: ...


class ActionGateway:
    def __init__(
        self,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        audit_file: AuditFile | None = None,
        history: list[AuditEntry] | None = None,
        idempotency: IdempotencyFile | None = None,
        receipts: ReceiptBook | None = None,
        approvals: ApprovalFile | None = None,
        anchor: Callable[[int, str], None] | None = None,
    ) -> None:
        self._anchor = anchor
        self._clock, self._lock, self._audit_file, self._idem_file, self._receipts = clock, threading.RLock(), audit_file, idempotency, receipts
        self._specs: dict[str, ActionSpec] = {}
        self._approval_file = approvals
        self._approvals: dict[str, Approval] = approvals.load() if approvals is not None else {}
        self._done: dict[str, _Done] = {}
        self._idem: dict[tuple[str, str], tuple[str, Outcome]] = idempotency.load() if idempotency is not None else {}
        self._revoked: set[str] = set()
        self.audit: list[AuditEntry] = list(history or [])  # a history loaded from disk continues the same chain
        self.prompts = 0  # approvals asked of the owner; reversible local work never moves it

    # -- registry ---------------------------------------------------------------------------------------------------------------------------
    def register(self, spec: ActionSpec) -> None:
        if spec.name in self._specs:
            raise ValueError("duplicate action")
        self._specs[spec.name] = spec

    def specs(self) -> list[ActionSpec]:
        return [self._specs[n] for n in sorted(self._specs)]

    def revoke_connector(self, connector: str) -> None:
        with self._lock:
            self._revoked.add(connector)

    def allow_connector(self, connector: str) -> None:
        """The owner connected it again: its actions are accepted again (a connector that was never connected has no credentials, so they fail rather than act)."""
        with self._lock:
            self._revoked.discard(connector)

    # -- audit ------------------------------------------------------------------------------------------------------------------------------
    def _log(self, action: str, outcome: str, code: str, payload_hash: str, approval_id: str | None) -> None:
        prev = self.audit[-1].digest if self.audit else GENESIS
        seq, at = len(self.audit) + 1, self._clock().isoformat()
        entry = AuditEntry(seq, at, action, outcome, code, payload_hash, approval_id, prev, "")
        entry = AuditEntry(seq, at, action, outcome, code, payload_hash, approval_id, prev, _digest_of(prev, entry))
        if self._audit_file is not None:
            self._audit_file.append(entry)  # on disk before the outcome is returned
        self.audit.append(entry)
        if self._anchor is not None:
            self._anchor(entry.seq, entry.digest)  # outside the audit file: a later deletion or truncation of the file is detected

    def verify_audit(self) -> bool:
        return _chain_ok(self.audit)

    # -- approvals: the owner-facing half ---------------------------------------------------------------------------------------------------
    def grant(self, approval_id: str, *, by_owner: bool) -> bool:
        """Called only by the code path that serves an enrolled owner client. `by_owner=False` (any other caller, any content) grants nothing."""
        with self._lock:
            approval = self._approvals.get(approval_id)
            if not by_owner or approval is None or approval.used or approval.expires_at < self._clock():
                return False
            approval.granted = True
            self._keep(approval)
            return True

    def _keep(self, approval: Approval) -> None:
        if self._approval_file is not None:
            self._approval_file.append(approval)

    def _consume(self, approval_id: str | None, binding: str, now: datetime) -> bool:
        approval = self._approvals.get(approval_id or "")
        if approval is None or not approval.granted or approval.used or approval.expires_at < now or approval.binding != binding:
            return False
        approval.used = True  # single-use: gone before the action runs
        self._keep(approval)  # and on disk before it runs, so a restart cannot use it again
        return True

    # -- the one door -----------------------------------------------------------------------------------------------------------------------
    def propose(self, name: str, payload: dict[str, Any], *, origin: str, idempotency_key: str, approval_id: str | None = None) -> Outcome:  # noqa: PLR0911 (one outcome per refusal reason is the point)
        spec, now = self._specs.get(name), self._clock()
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        with self._lock:
            if spec is None:
                return Outcome("refused", "unknown_action")
            if origin not in ORIGINS:
                return self._refuse(name, "unknown_origin", digest)
            if origin == "untrusted_content":
                return self._refuse(name, "untrusted_origin", digest)  # content cannot propose, and cannot approve
            if spec.connector in self._revoked:
                return self._refuse(name, "connector_revoked", digest)
            seen = self._idem.get((name, idempotency_key))
            if seen is not None:
                return seen[1] if seen[0] == digest else self._refuse(name, "idempotency_conflict", digest)
            category, binding = spec.category, binding_of(name, payload)
            if category is not None and not self._consume(approval_id, binding, now):
                pending = Approval(secrets.token_hex(8), binding, category, now + APPROVAL_TTL)
                self._approvals[pending.approval_id] = pending
                self._keep(pending)
                self.prompts += 1
                self._log(name, "needs_approval", f"category_{category}", digest, pending.approval_id)
                return Outcome("needs_approval", f"category_{category}", approval_id=pending.approval_id, category=category, exact_payload=dict(payload))
            external = spec.connector is not None or category is not None  # an effect outside Atlas's own transactional stores
            if external:
                # ATLAS-ACT-019: the intent is on disk BEFORE the effect, so a crash between the effect and its outcome is answered
                # `outcome_unknown` on a retry with the same key after the restart, and the effect never runs twice
                self._remember(name, idempotency_key, digest, Outcome("failed", "outcome_unknown"))
            try:
                result = spec.handler(dict(payload))
            except ActionNotPerformed:
                if external:
                    self._forget(name, idempotency_key, digest)
                self._log(name, "failed", "handler_failed", digest, approval_id)
                return Outcome("failed", "handler_failed")  # proven to have done nothing: the same key may be tried again
            except Exception:  # noqa: BLE001  (a handler's failure is a code; its text could carry content)
                if external:
                    return self._ambiguous(name, idempotency_key, digest, approval_id)
                self._log(name, "failed", "handler_failed", digest, approval_id)
                return Outcome("failed", "handler_failed")
            action_id = secrets.token_hex(8)
            self._done[action_id] = _Done(spec, dict(payload), dict(result))
            if self._receipts is not None:
                self._receipts.put_receipt(action_id, name, dict(payload), dict(result))  # durable before the outcome is returned
            outcome = Outcome("done", action_id=action_id, result=dict(result))
            self._remember(name, idempotency_key, digest, outcome)
            self._log(name, "done", "", digest, approval_id if category is not None else None)
            return outcome

    def _remember(self, name: str, key: str, digest: str, outcome: Outcome) -> None:
        self._idem[(name, key)] = (digest, outcome)
        if self._idem_file is not None:
            self._idem_file.append(name, key, digest, outcome)

    def _forget(self, name: str, key: str, digest: str) -> None:
        self._idem.pop((name, key), None)
        if self._idem_file is not None:
            self._idem_file.append(name, key, digest, Outcome("forgotten"))

    def _ambiguous(self, name: str, key: str, digest: str, approval_id: str | None) -> Outcome:
        """An external action failed without proof that it did nothing. It is recorded under its key, so a retry returns this answer instead of running the handler again; the owner reconciles with the provider."""
        outcome = Outcome("failed", "outcome_unknown")
        self._remember(name, key, digest, outcome)
        self._log(name, "failed", "outcome_unknown", digest, approval_id)
        return outcome

    def _refuse(self, name: str, code: str, digest: str) -> Outcome:
        self._log(name, "refused", code, digest, None)
        return Outcome("refused", code)

    def _from_receipt(self, action_id: str) -> _Done | None:
        """An action executed before a restart: rebuilt from its durable receipt, with the handler of the same name registered in this run."""
        found = self._receipts.receipt(action_id) if self._receipts is not None else None
        if found is None or found[0] not in self._specs:
            return None
        name, payload, result, undone = found
        done = _Done(self._specs[name], payload, result, undone)
        self._done[action_id] = done
        return done

    def undo(self, action_id: str) -> Outcome:
        with self._lock:
            done = self._done.get(action_id) or self._from_receipt(action_id)
            if done is None:
                return Outcome("refused", "unknown_action_id")
            if done.undone:
                return Outcome("refused", "already_undone")
            if done.spec.undo is None:
                return Outcome("refused", "not_reversible")
            digest = hashlib.sha256(_canonical(done.payload)).hexdigest()
            atomic = done.spec.atomic_undo is not None and self._receipts is not None
            try:
                if atomic:
                    assert done.spec.atomic_undo is not None
                    done.spec.atomic_undo(done.payload, done.result, action_id)  # the effect and the receipt's mark commit together
                else:
                    done.spec.undo(done.payload, done.result)
            except Exception:  # noqa: BLE001
                self._log(done.spec.name, "failed", "undo_failed", digest, None)
                return Outcome("failed", "undo_failed")
            done.undone = True
            if self._receipts is not None and not atomic:
                self._receipts.mark_undone(action_id)
            self._log(done.spec.name, "done", "undone", digest, None)
            return Outcome("done", "undone", action_id=action_id)


@dataclass
class WorkflowReport:
    status: str  # completed | cancelled | failed_rolled_back | failed_partial
    completed: list[str] = field(default_factory=list)
    compensated: list[str] = field(default_factory=list)
    stuck: list[str] = field(default_factory=list)  # steps whose effect could not be taken back
    detail: str = ""


def run_workflow(
    gateway: ActionGateway,
    steps: list[tuple[str, dict[str, Any]]],
    *,
    key: str,
    cancelled: Callable[[], bool] = lambda: False,
    approvals: dict[int, str] | None = None,
) -> WorkflowReport:
    """Run steps in order, each through the gateway as the owner's own request. A step that needs approval stops the workflow (`needs_approval`, nothing after it runs); a failure or a cancel takes back the
    completed steps in reverse order. A step that cannot be taken back is reported as stuck: the report says `failed_partial`, never that all is well."""
    report = WorkflowReport("completed")
    done: list[tuple[str, str]] = []
    for index, (name, payload) in enumerate(steps):
        if cancelled():
            report.status = "cancelled"
            break
        outcome = gateway.propose(name, payload, origin="owner_request", idempotency_key=f"{key}-{index}", approval_id=(approvals or {}).get(index))
        if outcome.status != "done":
            report.status, report.detail = ("needs_approval" if outcome.status == "needs_approval" else "failed_rolled_back"), outcome.code
            break
        done.append((name, outcome.action_id or ""))
        report.completed.append(name)
    if report.status in ("cancelled", "failed_rolled_back"):
        for name, action_id in reversed(done):
            if gateway.undo(action_id).status == "done":
                report.compensated.append(name)
            else:
                report.stuck.append(name)
        if report.stuck:
            report.status = "failed_partial"
    return report
