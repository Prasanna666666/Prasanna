"""The owner's actions and a device's sync, as one facade for the API (Stages 5 and 6).

It owns no rule: the Action Gateway decides approval, idempotency, undo and audit; the sync service applies a device's queue; this class only turns their results into the contract's shapes and fixes the
ORIGIN of everything that comes through the API to the owner's own request (a signed owner client). Content (a page, a message, a document) has no way to reach this class: it can only call the gateway
itself with the `untrusted_content` origin, which the gateway refuses.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .actions import ActionGateway, Outcome
from .devices import DeviceDirectory, DeviceError
from .errors import CoreError
from .recordstore import RecordStore
from .sync import QueuedOp, SyncService
from .watchers import calendar_conflicts


def _line(text: str) -> str:
    return " ".join(text.split())[:200]


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


DEFAULT_EVENT = timedelta(hours=1)  # an event with no end is treated as an hour long


def _moment(text: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class Operations:
    def __init__(self, gateway: ActionGateway, sync: SyncService, store: RecordStore | None = None) -> None:
        self._gateway, self._sync, self._store = gateway, sync, store

    def attention(self) -> dict[str, Any]:
        """What needs the owner's attention, by code, from the owner's own calendar: events whose times overlap. Records without a usable start are skipped, never guessed."""
        if self._store is None:
            return {"items": []}
        titles, events = {}, []
        for stored in self._store.in_domain("calendar"):
            start = _moment(stored.record.fields.get("starts", ""))
            if start is None:
                continue
            end = _moment(stored.record.fields.get("ends", "")) or start + DEFAULT_EVENT
            titles[stored.record.record_id] = stored.record.title
            events.append((stored.record.record_id, start, max(end, start)))
        items = []
        for n in calendar_conflicts(events)[:50]:
            first = n.dedupe_key.split(":")[1]
            items.append(
                {
                    "kind": n.kind,
                    "record_id": n.record_id,
                    "title": _line(f"“{titles.get(first, '')}” overlaps “{titles.get(n.record_id, '')}”"),
                    "priority": n.priority,
                    "key": n.dedupe_key,
                }
            )
        return {"items": items}

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


class DeviceOperations:
    """Device pairing and revocation for the API. Every refusal is the same user-safe error as everywhere else; a pairing guess learns nothing."""

    def __init__(self, directory: DeviceDirectory, identity_public_key: Ed25519PublicKey) -> None:
        self._directory, self._core_key = directory, identity_public_key

    def offer(self, by_client: str) -> dict[str, Any]:
        try:
            o = self._directory.open_offer(by_client)
        except DeviceError:
            raise CoreError("forbidden") from None
        return {"code": o.code, "core_fingerprint": o.core_fingerprint, "expires_at": o.expires_at.isoformat()}

    def pair(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            device_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(body["public_key"], validate=True))
            proof = self._directory.pair(body["code"], body["device_id"], body["label"], device_key, body["nonce"])
        except (DeviceError, ValueError):
            raise CoreError("forbidden") from None  # the same answer for a wrong code, an expired offer, a spent one or a malformed key
        return {"core_public_key": base64.b64encode(self._core_key.public_bytes_raw()).decode(), "proof": base64.b64encode(proof).decode()}

    def listing(self) -> dict[str, Any]:
        return {
            "devices": [
                {"device_id": d["device_id"], "label": d["label"] or "", "paired_at": d["paired_at"], "revoked_at": d["revoked_at"]}
                for d in self._directory.devices()
            ]
        }

    def revoke(self, by_client: str, device_id: str) -> dict[str, Any]:
        try:
            self._directory.revoke(by_client, device_id)
        except DeviceError as error:
            raise CoreError("not_found" if error.code == "unknown_device" else "forbidden") from None
        return {"revoked": True}
