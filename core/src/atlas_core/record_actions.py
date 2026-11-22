"""The standard local actions over the owner's own records, registered with the Action Gateway (Stage 5 and 6).

Calendar, Contacts and Notes changes are local and reversible, so they never prompt (PRD 4.4). Sending an invitation or update outside the Mac is category 1 and needs the owner's approval. Removing a
record for good is category 3 (no reliable undo) and needs approval. The `outbox` is the platform seam that would actually send something; in this stage it is a recording fake.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .actions import ActionGateway, ActionSpec
from .records import Record
from .recordstore import RecordStore, StoreError

Sender = Callable[[dict[str, Any]], dict[str, Any]]
PURGE_EFFECTS = frozenset({"local_irreversible"})


def register_record_actions(gateway: ActionGateway, store: RecordStore, outbox: Sender, purge: Callable[[str], None]) -> None:
    """`purge(record_id)` is the platform's irreversible removal: only the approval-gated action reaches it."""

    def create(domain: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def run(p: dict[str, Any]) -> dict[str, Any]:
            seq = store.create(Record(p["id"], domain, p["date"], p["title"], p.get("fields", {})))
            return {"id": p["id"], "seq": seq}

        return run

    def undo_change(_payload: dict[str, Any], result: dict[str, Any]) -> None:
        store.undo(result["seq"])

    def edit(p: dict[str, Any]) -> dict[str, Any]:
        return {"id": p["id"], "seq": store.update(p["id"], p["expected_version"], title=p.get("title"), date=p.get("date"), fields=p.get("fields"))}

    def soft_delete(p: dict[str, Any]) -> dict[str, Any]:
        return {"id": p["id"], "seq": store.delete(p["id"], p["expected_version"])}

    def erase(p: dict[str, Any]) -> dict[str, Any]:
        purge(p["id"])
        return {"id": p["id"]}

    local = frozenset({"local_reversible"})
    for domain in ("calendar", "contacts", "notes"):
        gateway.register(ActionSpec(f"{domain}.create", local, create(domain), undo_change))
        gateway.register(ActionSpec(f"{domain}.edit", local, edit, undo_change))  # moving an event is an edit of its date and fields
        gateway.register(ActionSpec(f"{domain}.archive", local, soft_delete, undo_change))
        gateway.register(ActionSpec(f"{domain}.erase", PURGE_EFFECTS, erase))
    gateway.register(ActionSpec("calendar.send_invitation", frozenset({"external_send"}), outbox))


__all__ = ["StoreError", "register_record_actions"]
