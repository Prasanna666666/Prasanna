"""The source policy: default deny, decided before anything is retrieved and before any text can reach a model.

A PermitToken is the proof of an allow decision. Only PolicyEngine can mint one (the mint is private to this module), so a retriever or a model
gateway that asks for a token cannot be handed a made-up one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from .rules import Rules, load_rules

PURPOSE = "answer_question"
_MINT = object()


class PolicyViolation(Exception):
    """Something tried to read or pass on content the policy did not allow. The text is a code, never content."""


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
    _mint: object = field(repr=False, default=None)

    def __post_init__(self) -> None:
        if self._mint is not _MINT:
            raise PolicyViolation("token_not_minted_by_policy")

    def allows(self, source_type: str, now: datetime) -> bool:
        return source_type in self.permitted and now < self.expires_at


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
        for source_type in dict.fromkeys(requested):
            reason, grant_id = self._judge(source_type, now, purpose)
            if reason == "granted":
                permitted.append(source_type)
                grant_ids.append(grant_id or "")
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
        return decision, PermitToken(frozenset(permitted), expiry, decision, _mint=_MINT)

    def _judge(self, source_type: str, now: datetime, purpose: str) -> tuple[str, str | None]:
        sensitivity = self._rules.sensitivity_of(source_type)
        if sensitivity is None:
            return "unknown_source_type", None
        if self._rules.is_restricted(source_type):
            return "restricted_domain", None  # Finance and Health never enter a general context, whatever a grant says
        if self._rules.deferred_to(source_type):
            return "deferred_decision", None
        return self._grant_verdict(self._grants.grants_for(source_type), sensitivity, now, purpose)

    def _grant_verdict(self, grants: list[dict[str, Any]], sensitivity: str, now: datetime, purpose: str) -> tuple[str, str | None]:
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
                return "granted", str(grant["grant_id"])
        return reason, None
