"""The only way to retrieve and the only way to reach a model: both need a PermitToken from the policy.

A retriever is called only for a source type the token allows, and what it returns is checked again. A model context is built only from passages
the token allows, and only a context built here can be given to a model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .evidence import SourceStore
from .policy import PermissionRevoked, PermitToken, PolicyEngine, PolicyViolation
from .rules import Rules, load_rules
from .values import LanguageIn

_CONTEXT_MINT = object()


class Retriever(Protocol):
    def search(self, source_type: str, query: str) -> Iterable[dict[str, Any]]: ...


class SourceLabels:
    """The trusted sensitivity of a passage. It is read from the source store (written by the side that stored the source, immutable per version) and NEVER from what a retriever
    returned: a retriever cannot make a sensitive item look less sensitive. An item whose source is unknown to the store, or whose source type disagrees with the one it claims,
    has no label, and an item without a label is never covered by any grant (it fails closed)."""

    def __init__(self, sources: SourceStore, rules: Rules | None = None) -> None:
        self._sources, self._rules = sources, rules or load_rules()

    def of(self, passage: dict[str, Any]) -> str | None:
        claimed = passage["evidence"]
        source = self._sources.get(claimed["source_id"])
        if source is None or source.source_type != claimed["source_type"]:
            return None
        label = source.sensitivity or self._rules.sensitivity_of(source.source_type)
        return label if label in self._rules.raw["sensitivity_order"] else None


class ModelUnavailable(Exception):
    """The local model cannot answer right now."""


@dataclass(frozen=True)
class ModelAnswer:
    """What a model returns: text, the citations it claims (checked later, never trusted) and the language it found."""

    text: str
    citations: tuple[dict[str, Any], ...] = ()
    language: LanguageIn = field(default_factory=LanguageIn)


class ModelGateway(Protocol):
    def generate(self, context: ModelContext) -> ModelAnswer: ...


@dataclass(frozen=True)
class ModelContext:
    question: str
    passages: tuple[dict[str, Any], ...]
    truncated: bool
    permit_id: str = ""  # the authorisation this context was built under
    _mint: object = field(repr=False, default=None)

    def __post_init__(self) -> None:
        if self._mint is not _CONTEXT_MINT:
            raise PolicyViolation("context_not_built_by_gate")


@dataclass(frozen=True)
class Retrieved:
    passages: list[dict[str, Any]]
    excluded_sensitive: int = 0  # items left out because they are more sensitive than the grant covers


class GatedRetrieval:
    def __init__(self, labels: SourceLabels) -> None:
        self._labels = labels

    def fetch(
        self,
        token: PermitToken,
        retriever: Retriever,
        query: str,
        now: datetime,
        policy: PolicyEngine | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> Retrieved:
        """Search each permitted source type. With a policy, the grants are re-checked immediately before EACH source is read (a revocation after the token was minted stops
        the next read), and items more sensitive than the grant covers are excluded and counted."""
        out: list[dict[str, Any]] = []
        excluded = 0
        for source_type in sorted(token.permitted):
            moment = clock() if clock is not None else now
            if policy is not None:
                current, denied = policy.revalidate(token, moment)
                if source_type not in current or denied:
                    raise PermissionRevoked(denied)
            if not token.allows(source_type, moment):
                continue
            for passage in retriever.search(source_type, query):
                if not token.allows(passage["evidence"]["source_type"], moment):
                    raise PolicyViolation("retriever_returned_denied_source")
                if not token.allows_item(passage["evidence"]["source_type"], self._labels.of(passage), moment):
                    excluded += 1
                    continue
                out.append(passage)
        return Retrieved(out, excluded)


class ContextBuilder:
    def __init__(self, labels: SourceLabels, rules: Rules | None = None) -> None:
        self._labels, self._budget = labels, (rules or load_rules()).limit("context_chars")

    def build(self, token: PermitToken, question: str, passages: Sequence[dict[str, Any]], now: datetime) -> ModelContext:
        kept: list[dict[str, Any]] = []
        used = 0
        for passage in passages:
            if not token.allows_item(passage["evidence"]["source_type"], self._labels.of(passage), now):
                raise PolicyViolation("passage_not_permitted")
            if used + len(passage["text"]) > self._budget:
                continue  # dropped, and said so: truncated is carried to the answer's limitations
            kept.append(passage)
            used += len(passage["text"])
        return ModelContext(question, tuple(kept), len(kept) < len(passages), token.permit_id, _CONTEXT_MINT)


class GatedModel:
    """The one door to a model. It re-checks the token, and (with a policy) the grants as they are now, so a model is never called under an expired, missing or revoked permission."""

    def __init__(self, model: ModelGateway, labels: SourceLabels, policy: PolicyEngine | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self._model, self._labels, self._policy, self._clock = model, labels, policy, clock

    def generate(self, token: PermitToken, context: ModelContext, now: datetime) -> ModelAnswer:
        moment = self._clock() if self._clock is not None else now
        if moment >= token.expires_at:
            raise PolicyViolation("token_expired")
        if context.permit_id != token.permit_id:
            raise PolicyViolation("context_built_under_another_authorisation")
        for passage in context.passages:  # re-checked at the door itself: a context carried over from a broader token cannot pass
            if not token.allows_item(passage["evidence"]["source_type"], self._labels.of(passage), moment):
                raise PolicyViolation("passage_not_permitted")
        if self._policy is not None:
            current, denied = self._policy.revalidate(token, moment)
            if denied and any(p["evidence"]["source_type"] not in current for p in context.passages):
                raise PermissionRevoked(denied)
        return self._model.generate(context)
