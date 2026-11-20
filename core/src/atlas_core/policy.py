"""The source policy: default deny, decided before anything is retrieved and before any text can reach a model.

A PermitToken is the proof of an allow decision. Only PolicyEngine can mint one (the mint is private to this module), so a retriever or a model
gateway that asks for a token cannot be handed a made-up one.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from .rules import Rules, load_rules

PURPOSE = "answer_question"
_MINT = object()


class PolicyViolation(Exception):
    """Something tried to read or pass on content the policy did not allow. The text is a code, never content."""


class PermissionRevoked(PolicyViolation):
    """A permission that was valid when the task started is no longer valid now. Carries the denied source types (codes only, no content)."""

    def __init__(self, denied: list[dict[str, str]]) -> None:
        super().__init__("permission_revoked")
        self.denied = denied


class GrantSource(Protocol):
    def grants_for(self, source_type: str) -> list[dict[str, Any]]: ...


class InMemoryGrants:
    """Owner designations as SourceGrant records. How the owner creates one is a later decision (G-O19); this slice only reads them."""

    def __init__(self, grants: Sequence[dict[str, Any]] = ()) -> None:
        self._grants = list(grants)

    def add(self, grant: dict[str, Any]) -> None:
        self._grants.append(grant)

    def grants_for(self, source_type: str) -> list[dict[str, Any]]:
        return [g for g in self._grants if g["source_type"] == source_type]


@dataclass(frozen=True)
class PermitToken:
    permitted: frozenset[str]
    expires_at: datetime
    decision: dict[str, Any] = field(repr=False)
    permit_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # identifies this one authorisation: a context is bound to it
    grants: Mapping[str, tuple[str, str]] = field(
        default_factory=dict, repr=False
    )  # per source type: (grant id, the most sensitive item that grant covers) AT MINT
    order: tuple[str, ...] = field(default=(), repr=False)  # sensitivity order, lowest first
    _mint: object = field(repr=False, default=None)

    def __post_init__(self) -> None:
        if self._mint is not _MINT:
            raise PolicyViolation("token_not_minted_by_policy")

    def allows(self, source_type: str, now: datetime) -> bool:
        return source_type in self.permitted and now < self.expires_at

    def allows_item(self, source_type: str, sensitivity: str | None, now: datetime) -> bool:
        """The source type is permitted AND an item of this sensitivity is covered by the grant. The sensitivity must be the TRUSTED label of the item (from the source store, see
        gate.SourceLabels); a missing or unknown label is never covered, so an unlabelled item fails closed."""
        if not self.allows(source_type, now) or sensitivity not in self.order:
            return False
        return self.order.index(sensitivity) <= self.order.index(self.grants[source_type][1])


def _parse(stamp: str | None) -> datetime | None:
    return None if stamp is None else datetime.fromisoformat(stamp.replace("Z", "+00:00"))


class PolicyEngine:
    def __init__(self, grants: GrantSource, rules: Rules | None = None) -> None:
        self._grants, self._rules = grants, rules or load_rules()

    def decide(self, requested: Sequence[str], now: datetime, purpose: str = PURPOSE) -> tuple[dict[str, Any], PermitToken | None]:
        """A PolicyDecision for the requested source types and, when something is allowed, the token that proves it. Default is deny."""
        permitted: list[str] = []
        denied: list[dict[str, str]] = []
        grant_ids: list[str] = []
        bound: dict[str, tuple[str, str]] = {}
        for source_type in dict.fromkeys(requested):
            reason, grant_id, ceiling = self._judge(source_type, now, purpose)
            if reason == "granted":
                permitted.append(source_type)
                grant_ids.append(grant_id or "")
                bound[source_type] = (grant_id or "", ceiling or "")
            else:
                denied.append({"source_type": source_type, "reason_code": reason})
        decision: dict[str, Any] = {
            "decision": "allow" if permitted else "deny",
            "policy_version": self._rules.version,
            "reason_code": "granted" if permitted else (denied[0]["reason_code"] if denied else "nothing_requested"),
            "permitted_source_types": permitted,
            "denied": denied,
        }
        if grant_ids:
            decision["grant_ids"] = [g for g in grant_ids if g]
        if not permitted:
            return decision, None
        expiry = now + timedelta(seconds=self._rules.limit("token_seconds"))
        order = tuple(self._rules.raw["sensitivity_order"])
        return decision, PermitToken(frozenset(permitted), expiry, decision, grants=bound, order=order, _mint=_MINT)

    def revalidate(self, token: PermitToken, now: datetime, purpose: str = PURPOSE) -> tuple[frozenset[str], list[dict[str, str]]]:
        """Re-check, against the grants as they are NOW, every source type the token was minted for. Used immediately before a source is read and again at the model door,
        so a change after the token was minted takes effect before anything more is read or sent. A source type stays valid only while the SAME grant (its identity) with the SAME
        ceiling still allows it: a revoke followed by a new grant, or a changed scope or ceiling, ends the token's authority for that type (reported as grant_revoked), even
        though the type itself would still be allowed under the new grant. A token never gains anything from a broader or newer grant."""
        still: set[str] = set()
        denied: list[dict[str, str]] = []
        for source_type in sorted(token.permitted):
            reason, grant_id, ceiling = self._judge(source_type, now, purpose)
            if reason == "granted" and token.grants.get(source_type) != (grant_id, ceiling):
                reason = "grant_revoked"  # the grant this authorisation was minted under is gone or changed
            if reason == "granted":
                still.add(source_type)
            else:
                denied.append({"source_type": source_type, "reason_code": reason})
        return frozenset(still), denied

    def _judge(self, source_type: str, now: datetime, purpose: str) -> tuple[str, str | None, str | None]:
        sensitivity = self._rules.sensitivity_of(source_type)
        if sensitivity is None:
            return "unknown_source_type", None, None
        if self._rules.is_restricted(source_type):
            return "restricted_domain", None, None  # Finance and Health never enter a general context, whatever a grant says
        if self._rules.deferred_to(source_type):
            return "deferred_decision", None, None
        return self._grant_verdict(self._grants.grants_for(source_type), sensitivity, now, purpose)

    def _grant_verdict(self, grants: list[dict[str, Any]], sensitivity: str, now: datetime, purpose: str) -> tuple[str, str | None, str | None]:
        reason = "no_grant"
        for grant in grants:
            if grant["purpose"] != purpose:
                continue
            if grant["revoked"]:
                reason = "grant_revoked"
            elif (expiry := _parse(grant["expires_at"])) is not None and expiry <= now:
                reason = "grant_expired"
            elif self._rules.rank(grant["max_sensitivity"]) < self._rules.rank(sensitivity):
                reason = "sensitivity_exceeds_grant"
            else:
                return "granted", str(grant["grant_id"]), str(grant["max_sensitivity"])
        return reason, None, None
