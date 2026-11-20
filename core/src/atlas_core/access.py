"""The gate in front of every source adapter: a source may be touched only while the owner's grant is current AND the operating system currently says it may be read.

`SourceAccess` is the `GrantSource` the policy engine consumes, so the existing policy stays the single decision point (grant, ceiling, expiry, restricted and deferred types); it adds
the one thing policy cannot know: the platform permission. The OS answer is asked for at every check, as positive, current evidence from the platform adapter; a stored consent, a flag
a caller passes, or an environment variable is never proof of it. When a permission that was once granted is positively reported lost, the grant is revoked (a new grant identity is
needed later) and what was derived from it is purged.

OS permission discovery on macOS (TCC) is NOT implemented here: `OSPermissionProvider` is the seam, `FakeOSPermissions` the deterministic CI stand-in.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .designation import DesignationStore, StoreCorrupt
from .policy import PermissionRevoked, PolicyEngine
from .rules import Rules, load_rules

GRANTED, MISSING, UNKNOWN = "granted", "missing", "unknown"  # the 1.1 ConsentState.os_access values
MAX_EVIDENCE_AGE = timedelta(seconds=30)


@dataclass(frozen=True)
class PermissionEvidence:
    """What the platform adapter observed: which source type, what it found, and when."""

    source_type: str
    state: str  # granted, missing (denied or revoked) or unknown (not yet decided, or could not be determined)
    observed_at: datetime


class OSPermissionProvider(Protocol):
    def current(self, source_type: str) -> PermissionEvidence: ...


class AccessCheck(Protocol):
    """What a source adapter asks before it starts, scans, indexes, searches or reads."""

    def permitted(self, source_type: str) -> bool: ...


class FakeOSPermissions:
    """Deterministic stand-in for the platform provider in Linux CI. It starts with nothing decided (unknown), like a fresh install. NOT evidence of any macOS behaviour."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._state: dict[str, str] = {}
        self.fail = False  # the provider itself errors
        self.stale_by: timedelta | None = None  # the provider reports an observation this much older than now
        self.calls: list[str] = []

    def set(self, source_type: str, state: str) -> None:
        self._state[source_type] = state

    def current(self, source_type: str) -> PermissionEvidence:
        self.calls.append(source_type)
        if self.fail:
            raise OSError("provider unavailable")
        moment = self._clock() - (self.stale_by or timedelta(0))
        return PermissionEvidence(source_type, self._state.get(source_type, UNKNOWN), moment)


class AllowAll:
    """TEST ONLY: an access check that always permits. Production code must be given a SourceAccess; there is no default."""

    def permitted(self, source_type: str) -> bool:
        return True


class SourceAccess:
    def __init__(
        self,
        designations: DesignationStore,
        provider: OSPermissionProvider,
        clock: Callable[[], datetime] | None = None,
        rules: Rules | None = None,
        max_age: timedelta = MAX_EVIDENCE_AGE,
    ) -> None:
        self._designations, self._provider, self._max_age = designations, provider, max_age
        self._clock = clock or (lambda: datetime.now(UTC))
        self._policy = PolicyEngine(self, rules or load_rules())

    # -- the OS side ------------------------------------------------------------------------------------------------------------------------------
    def os_access(self, source_type: str) -> str:
        """granted only on fresh, positive evidence for exactly this source type. An error, stale or future-dated evidence, or evidence about another type is 'unknown'."""
        try:
            evidence = self._provider.current(source_type)
        except Exception:  # noqa: BLE001  (any provider failure is simply 'no evidence': fail closed)
            return UNKNOWN
        age = self._clock() - evidence.observed_at
        if evidence.source_type != source_type or age > self._max_age or age < -self._max_age:
            return UNKNOWN
        return evidence.state if evidence.state in (GRANTED, MISSING) else UNKNOWN

    # -- GrantSource: what the policy engine reads ------------------------------------------------------------------------------------------------------
    def grants_for(self, source_type: str) -> list[dict[str, Any]]:
        try:
            return self._grants_for(source_type)
        except StoreCorrupt:
            return []  # a record that cannot be trusted grants nothing

    def _grants_for(self, source_type: str) -> list[dict[str, Any]]:
        self._designations.sweep(self._clock())  # an expired grant is revoked, and its data purged, before anything else is judged
        grants = self._designations.grants_for(source_type)
        if all(g["revoked"] for g in grants):
            return grants
        state = self.os_access(source_type)
        if state == GRANTED:
            self._designations.note_os_granted(source_type)
            return grants
        if state == MISSING and self._designations.os_was_granted(source_type):
            self._designations.revoke(source_type, "os_permission_lost")  # the platform took the permission back: the grant ends and its data goes
            return self._designations.grants_for(source_type)
        return [g for g in grants if g["revoked"]]  # not (yet) permitted by the platform: no effective grant, the owner's consent is kept

    # -- AccessCheck: what an adapter asks -----------------------------------------------------------------------------------------------------------------
    def permitted(self, source_type: str) -> bool:
        """True only if the policy engine allows the source type right now (owner grant current, ceiling, expiry) and the platform permission is currently evidenced."""
        _, token = self._policy.decide([source_type], self._clock())
        return token is not None

    def require(self, source_type: str) -> None:
        if not self.permitted(source_type):
            raise PermissionRevoked([{"source_type": source_type, "reason_code": "grant_revoked"}])

    # -- the owner-facing state (the 1.1 ConsentState shape; not served) ------------------------------------------------------------------------------------
    def consent_state(self) -> dict[str, Any]:
        types = self._designations.designable()
        return {
            "grants": self._designations.latest_grants(types),
            "sources": [{"source_type": t, "os_access": self.os_access(t)} for t in types],
        }
