"""Offline edits from a remote device, applied safely (Stage 8): offline queue, idempotent replay, conflicts reported and never silently overwritten.

A device that has been offline keeps an ordered queue of operations, each with a unique id and the record VERSION it was made against. When it reconnects it sends the queue to the Core, which applies each
operation to the owner's own records (Calendar, Contacts, Notes) through the same versioned store and the same Action Gateway as the Mac app:

* **Replay is safe.** An operation id the Core has already applied is answered `duplicate` and changes nothing.
* **Conflicts are reported.** An edit made against an old version is a `conflict` that returns the Core's current version for the device to resolve; it never overwrites.
* **The device has no extra authority.** A revoked device's whole queue is `rejected`; a restricted domain (Finance, Health) or any domain the store does not hold is `rejected`; nothing about the queue
  can trigger an action that needs approval (those operations do not exist in the queue vocabulary).
* **Device caches hold only what was authorised and expire.** `CachePolicy` names what a device may keep (the records it is authorised for) and for how long; the revocation answer tells the device to wipe it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .actions import ActionGateway
from .identity import ClientRegistry

QUEUE_OPS = frozenset(
    {
        "calendar.create",
        "calendar.edit",
        "calendar.archive",
        "contacts.create",
        "contacts.edit",
        "contacts.archive",
        "notes.create",
        "notes.edit",
        "notes.archive",
        "travel.create",
        "travel.edit",
        "travel.archive",
    }
)
MAX_OPS = 500
CACHE_TTL = timedelta(days=7)


@dataclass(frozen=True)
class QueuedOp:
    op_id: str
    name: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class OpResult:
    op_id: str
    status: str  # applied | duplicate | conflict | rejected
    code: str = ""
    current_version: int | None = None


class OfflineQueue:
    """The device side: an ordered, durable-by-the-caller list of operations."""

    def __init__(self) -> None:
        self.ops: list[QueuedOp] = []

    def add(self, op_id: str, name: str, payload: dict[str, Any]) -> None:
        if name not in QUEUE_OPS:
            raise ValueError("not an operation a device may queue")  # approval-gated actions are not in the vocabulary at all
        if any(o.op_id == op_id for o in self.ops):
            raise ValueError("duplicate op id")
        self.ops.append(QueuedOp(op_id, name, payload))


class SyncService:
    def __init__(self, gateway: ActionGateway, registry: ClientRegistry, version_of: Callable[[str], int | None]) -> None:
        self._gateway, self._registry, self._version_of = gateway, registry, version_of
        self._applied: dict[tuple[str, str], OpResult] = {}  # (device, op id) -> its recorded result

    def apply(self, device_id: str, ops: list[QueuedOp]) -> list[OpResult]:
        if not self._registry.known(device_id) or self._is_revoked(device_id) or len(ops) > MAX_OPS:
            return [OpResult(o.op_id, "rejected", "device_not_allowed") for o in ops]
        results = []
        for op in ops:
            seen = self._applied.get((device_id, op.op_id))
            if seen is not None:
                results.append(OpResult(op.op_id, "duplicate", current_version=seen.current_version))
                continue
            result = self._one(device_id, op)
            if result.status in ("applied", "conflict"):
                self._applied[(device_id, op.op_id)] = result  # a conflict is final for this op id: the device resolves it with a NEW op
            results.append(result)
        return results

    def _is_revoked(self, device_id: str) -> bool:
        return not self._registry.is_active(device_id)

    def _one(self, device_id: str, op: QueuedOp) -> OpResult:
        if op.name not in QUEUE_OPS:
            return OpResult(op.op_id, "rejected", "operation_not_allowed")
        outcome = self._gateway.propose(op.name, op.payload, origin="owner_request", idempotency_key=f"{device_id}:{op.op_id}")
        if outcome.status == "done":
            return OpResult(op.op_id, "applied", current_version=self._version_of(op.payload.get("id", "")))
        if outcome.status == "failed":  # the store refused: a stale version (or a record that is not there)
            return OpResult(op.op_id, "conflict", "stale_or_missing", self._version_of(op.payload.get("id", "")))
        return OpResult(op.op_id, "rejected", outcome.code or outcome.status)


@dataclass(frozen=True)
class CachePolicy:
    domains: frozenset[str]
    expires_at: datetime
    wipe_on_revocation: bool = True


def cache_policy(authorised_domains: frozenset[str], now: datetime | None = None) -> CachePolicy:
    """What a device may keep: only the owner's own-record domains it is authorised for, for a limited time. Finance and Health are never cached on a device (the Core's rules keep them local)."""
    allowed = frozenset({"calendar", "contacts", "notes", "travel"}) & authorised_domains
    return CachePolicy(allowed, (now or datetime.now(UTC)) + CACHE_TTL)
