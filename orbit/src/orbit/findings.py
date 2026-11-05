"""The two plain records every checker speaks in. They live here, below every checker, so that no module has to import `verify` just to say "this is fine" or "this is wrong"."""

from __future__ import annotations

from dataclasses import dataclass, field

from .statements import Txn


@dataclass(frozen=True)
class Finding:
    agent: str
    level: str  # ok | warn | fail
    subject: str
    message: str


@dataclass
class Read:
    """The result of reading one statement file."""

    txns: list[Txn] = field(default_factory=list)
    status: str = "needs_check"  # verified | unverified | needs_check
    issues: list[str] = field(default_factory=list)
    account: str = ""
    first: str = ""
    last: str = ""
    opening: int | None = None
    closing: int | None = None
    proofs: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    currency: str = ""
