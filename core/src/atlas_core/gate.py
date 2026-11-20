"""The only way to retrieve and the only way to reach a model: both need a PermitToken from the policy.

A retriever is called only for a source type the token allows, and what it returns is checked again. A model context is built only from passages
the token allows, and only a context built here can be given to a model.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .policy import PermitToken, PolicyViolation
from .rules import Rules, load_rules
from .values import LanguageIn

_CONTEXT_MINT = object()


class Retriever(Protocol):
    def search(self, source_type: str, query: str) -> Iterable[dict[str, Any]]: ...


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


class GatedRetrieval:
    def fetch(self, token: PermitToken, retriever: Retriever, query: str, now: datetime) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for source_type in sorted(token.permitted):
            if not token.allows(source_type, now):
                continue
            for passage in retriever.search(source_type, query):
                if not token.allows(passage["evidence"]["source_type"], now):
                    raise PolicyViolation("retriever_returned_denied_source")
                out.append(passage)
        return out


class ContextBuilder:
    def __init__(self, rules: Rules | None = None) -> None:
        self._budget = (rules or load_rules()).limit("context_chars")

    def build(self, token: PermitToken, question: str, passages: Sequence[dict[str, Any]], now: datetime) -> ModelContext:
        kept: list[dict[str, Any]] = []
        used = 0
        for passage in passages:
            if not token.allows(passage["evidence"]["source_type"], now):
                raise PolicyViolation("passage_not_permitted")
            if used + len(passage["text"]) > self._budget:
                continue  # dropped, and said so: truncated is carried to the answer's limitations
            kept.append(passage)
            used += len(passage["text"])
        return ModelContext(question, tuple(kept), len(kept) < len(passages), token.permit_id, _CONTEXT_MINT)


class GatedModel:
    """The one door to a model. It re-checks the token, so a model is never called under an expired or missing permission."""

    def __init__(self, model: ModelGateway) -> None:
        self._model = model

    def generate(self, token: PermitToken, context: ModelContext, now: datetime) -> ModelAnswer:
        if now >= token.expires_at:
            raise PolicyViolation("token_expired")
        if context.permit_id != token.permit_id:
            raise PolicyViolation("context_built_under_another_authorisation")
        for passage in context.passages:  # re-checked at the door itself: a context carried over from a broader token cannot pass
            if not token.allows(passage["evidence"]["source_type"], now):
                raise PolicyViolation("passage_not_permitted")
        return self._model.generate(context)
