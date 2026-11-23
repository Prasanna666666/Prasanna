"""The owner's consent and the index status, as the API serves them (API 1.1: `/v1/consent`, `/v1/consent/{grant_id}`, `/v1/index/status`).

A thin layer over the designation store and the access gate: it adds no rule. A change needs a single-use request id (the API passes the signed request's nonce, so a replayed
request changes nothing), is audited by the store, and a revocation purges everything derived from the source through the purge the composition root registered. Errors become the
fixed taxonomy; the text of an exception never reaches a response.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .access import SourceAccess
from .designation import DesignationError, DesignationStore, OnboardingDecision, PurgePending, StoreCorrupt
from .errors import CoreError


class ConsentService:
    def __init__(self, designation: DesignationStore, access: SourceAccess, indexes: Mapping[str, Any], requester: Callable[[str], None] | None = None) -> None:
        self._requester = requester  # asks the operating system for a source's permission, once, when the owner turns that source on
        self._designation, self._access, self._indexes = designation, access, indexes

    def state(self) -> dict[str, Any]:
        try:
            return self._access.consent_state()
        except StoreCorrupt:
            raise CoreError("internal_error") from None

    def enable(self, sources: list[str], request_id: str) -> dict[str, Any]:
        try:
            self._designation.apply(OnboardingDecision(enable=frozenset(sources)), request_id)
        except DesignationError as error:
            raise _translate(error) from None
        for source in sources:
            self._ask_platform(source)
        return self.state()

    def _ask_platform(self, source: str) -> None:
        if self._requester is None:
            return
        try:
            self._requester(source)  # the system's own prompt appears here and nowhere else; a failure just leaves the permission undecided
        except Exception:  # noqa: BLE001
            return

    def revoke(self, grant_id: str, request_id: str) -> dict[str, Any]:
        source_type = next((g["source_type"] for g in self.state()["grants"] if g["grant_id"] == grant_id and not g["revoked"]), None)
        if source_type is None:
            raise CoreError("not_found")
        try:
            self._designation.withdraw(source_type, request_id)
        except DesignationError as error:
            raise _translate(error) from None
        return self.state()

    def index_status(self) -> dict[str, Any]:
        """Counts only, summed over the indexes that are currently permitted (a source without a current grant contributes nothing and is not described)."""
        indexed = total = pending = 0
        failed: dict[str, int] = {}
        unknown = building = False
        for source_type, index in self._indexes.items():
            if not self._access.permitted(source_type):
                continue
            report = index.coverage()
            indexed += report["searched"]
            total += report["total"]
            pending += report["pending"]
            building = building or not report["scan_complete"] or report["paused"] is not None or report["pending"] > 0
            for reason, count in report.get("failed_reasons", {}).items():
                code = _FAILED.get(reason, "extraction_failed")
                failed[code] = failed.get(code, 0) + count
        state = "building" if building else ("needs_attention" if failed else "idle")
        return {
            "state": state,
            "indexed": indexed,
            "total": None if unknown else total,
            "newest_indexed": None,  # not tracked: unknown, never guessed
            "failed": [{"reason_code": k, "count": v} for k, v in sorted(failed.items())],
        }


_FAILED = {"corrupt": "corrupt", "oversized": "too_large", "unreadable": "extraction_failed", "malformed_message": "corrupt"}


def _translate(error: DesignationError) -> CoreError:
    if isinstance(error, PurgePending):
        return CoreError("conflict")
    return CoreError(
        {"replayed": "conflict", "invalid_decision": "invalid_request", "invalid_request_id": "invalid_request", "withdraw_instead": "invalid_request"}.get(
            str(error), "internal_error"
        )
    )
