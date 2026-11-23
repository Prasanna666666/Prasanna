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
import secrets
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class ActionSpec:
    name: str
    effects: frozenset[str]
    handler: Handler
    undo: Undo | None = None
    connector: str | None = None

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


class ActionGateway:
    def __init__(
        self, clock: Callable[[], datetime] = lambda: datetime.now(UTC), audit_file: AuditFile | None = None, history: list[AuditEntry] | None = None
    ) -> None:
        self._clock, self._lock, self._audit_file = clock, threading.RLock(), audit_file
        self._specs: dict[str, ActionSpec] = {}
        self._approvals: dict[str, Approval] = {}
        self._done: dict[str, _Done] = {}
        self._idem: dict[tuple[str, str], tuple[str, Outcome]] = {}
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
            return True

    def _consume(self, approval_id: str | None, binding: str, now: datetime) -> bool:
        approval = self._approvals.get(approval_id or "")
        if approval is None or not approval.granted or approval.used or approval.expires_at < now or approval.binding != binding:
            return False
        approval.used = True  # single-use: gone before the action runs
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
                self.prompts += 1
                self._log(name, "needs_approval", f"category_{category}", digest, pending.approval_id)
                return Outcome("needs_approval", f"category_{category}", approval_id=pending.approval_id, category=category, exact_payload=dict(payload))
            try:
                result = spec.handler(dict(payload))
            except Exception:  # noqa: BLE001  (a handler's failure is a code; its text could carry content)
                self._log(name, "failed", "handler_failed", digest, approval_id)
                return Outcome("failed", "handler_failed")
            action_id = secrets.token_hex(8)
            self._done[action_id] = _Done(spec, dict(payload), dict(result))
            outcome = Outcome("done", action_id=action_id, result=dict(result))
            self._idem[(name, idempotency_key)] = (digest, outcome)
            self._log(name, "done", "", digest, approval_id if category is not None else None)
            return outcome

    def _refuse(self, name: str, code: str, digest: str) -> Outcome:
        self._log(name, "refused", code, digest, None)
        return Outcome("refused", code)

    def undo(self, action_id: str) -> Outcome:
        with self._lock:
            done = self._done.get(action_id)
            if done is None:
                return Outcome("refused", "unknown_action_id")
            if done.undone:
                return Outcome("refused", "already_undone")
            if done.spec.undo is None:
                return Outcome("refused", "not_reversible")
            digest = hashlib.sha256(_canonical(done.payload)).hexdigest()
            try:
                done.spec.undo(done.payload, done.result)
            except Exception:  # noqa: BLE001
                self._log(done.spec.name, "failed", "undo_failed", digest, None)
                return Outcome("failed", "undo_failed")
            done.undone = True
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
