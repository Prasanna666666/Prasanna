"""Exact evidence: a citation points into one immutable version of a source and is checked deterministically; anything that does not check fails closed."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol


class CitationError(Exception):
    """A citation failed. `reason` is a code; no content."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class StoredSource:
    source_id: str
    source_type: str
    text: str
    page_starts: tuple[int, ...] = ()
    blocks: tuple[tuple[int, int], ...] = ()
    parts: dict[str, tuple[int, int]] = field(default_factory=dict)
    sensitivity: str | None = None  # the TRUSTED label of this source, set by the side that stored it (never by a retriever); None means the type's default

    @property
    def version_sha256(self) -> str:
        return sha256_text(self.text)


class SourceStore(Protocol):
    def get(self, source_id: str) -> StoredSource | None: ...


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bounds(locator: dict[str, Any], source: StoredSource) -> tuple[int, int]:
    kind = locator["kind"]
    try:
        if kind == "page":
            start = source.page_starts[locator["page"] - 1]
            end = source.page_starts[locator["page"]] if locator["page"] < len(source.page_starts) else len(source.text)
            return start, end
        if kind == "block":
            return source.blocks[locator["block"]]
        if kind == "message_part":
            return source.parts[locator["message_part"]]
    except (IndexError, KeyError):
        raise CitationError("locator_mismatch") from None
    if kind == "span_only":
        return 0, len(source.text)
    raise CitationError("locator_mismatch")


def resolve(ref: dict[str, Any], store: SourceStore) -> str:
    """The exact text a reference points at, or CitationError. Stale (different version), wrong type, outside the locator or outside the text: all fail."""
    source = store.get(ref["source_id"])
    if source is None:
        raise CitationError("unresolvable")
    if source.version_sha256 != ref["version_sha256"]:
        raise CitationError("stale")
    if source.source_type != ref["source_type"]:
        raise CitationError("type_mismatch")
    start, end = ref["span"]["start"], ref["span"]["end"]
    low, high = _bounds(ref["locator"], source)
    if not (0 <= start < end <= len(source.text)) or not (low <= start and end <= high):
        raise CitationError("out_of_range")
    return source.text[start:end]


def check_citation(citation: dict[str, Any], store: SourceStore) -> str:
    """The cited span's text if the citation holds; a quote must appear verbatim inside it."""
    text = resolve(citation["evidence"], store)
    if "quote" in citation and citation["quote"] not in text:
        raise CitationError("quote_mismatch")
    return text
