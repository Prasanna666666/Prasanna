"""The owner's actions and a device's sync, as one facade for the API (Stages 5 and 6).

It owns no rule: the Action Gateway decides approval, idempotency, undo and audit; the sync service applies a device's queue; this class only turns their results into the contract's shapes and fixes the
ORIGIN of everything that comes through the API to the owner's own request (a signed owner client). Content (a page, a message, a document) has no way to reach this class: it can only call the gateway
itself with the `untrusted_content` origin, which the gateway refuses.
"""

from __future__ import annotations

from typing import Any

from .actions import ActionGateway, Outcome
from .sync import QueuedOp, SyncService


def _outcome(o: Outcome) -> dict[str, Any]:
    return {
        "status": o.status,
        "code": o.code,
        "action_id": o.action_id,
        "result": o.result,
        "approval_id": o.approval_id,
        "category": o.category,
        "exact_payload": o.exact_payload,
    }


class Operations:
    def __init__(self, gateway: ActionGateway, sync: SyncService) -> None:
        self._gateway, self._sync = gateway, sync

    def act(self, action: str, payload: dict[str, Any], idempotency_key: str, approval_id: str | None) -> dict[str, Any]:
        return _outcome(self._gateway.propose(action, payload, origin="owner_request", idempotency_key=idempotency_key, approval_id=approval_id))

    def approve(self, approval_id: str) -> dict[str, Any]:
        return {"granted": self._gateway.grant(approval_id, by_owner=True)}  # reached only through the owner-client check in the API

    def undo(self, action_id: str) -> dict[str, Any]:
        return _outcome(self._gateway.undo(action_id))

    def sync(self, device_id: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
        queue = [QueuedOp(o["op_id"], o["name"], o["payload"]) for o in ops]
        return {
            "results": [
                {"op_id": r.op_id, "status": r.status, "code": r.code, "current_version": r.current_version} for r in self._sync.apply(device_id, queue)
            ]
        }
