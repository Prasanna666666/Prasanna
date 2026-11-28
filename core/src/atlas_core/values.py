"""Small value types shared by several layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageIn:
    """What a reader or model reports about the language of a source or answer."""

    detected: str | None = None
    requested: str | None = None
    confidence: float | None = None
    path_unsupported: bool = False  # a reader, OCR or model path is known not to work for this language
