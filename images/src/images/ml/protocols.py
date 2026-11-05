"""Ports for the three ML capabilities.

The rest of Aperture depends only on these Protocols, never on torch, onnx or
PyObjC.  That is what makes the indexing pipeline unit-testable with tiny
fakes and lets you swap a model (say, a bigger CLIP) without touching callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class DetectedFace:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 in image pixels
    score: float
    embedding: np.ndarray  # float32, L2-normalised


@runtime_checkable
class ImageEmbedder(Protocol):
    """Maps images and text into one shared, L2-normalised vector space."""

    model_id: str  # e.g. "ViT-B-32/laion2b_s34b_b79k"

    def preprocess(self, image: Any) -> Any:
        """PIL image -> opaque tensor.  Must be safe to call from worker threads."""

    def embed_prepared(self, prepared: list[Any]) -> np.ndarray:
        """Batch of ``preprocess`` outputs -> ``(n, d)`` float32."""

    def embed_text(self, texts: list[str]) -> np.ndarray:
        """Strings -> ``(n, d)`` float32."""

    def close(self) -> None:
        """Release GPU / unified memory."""


@runtime_checkable
class FaceAnalyzer(Protocol):
    def analyse(self, bgr: np.ndarray) -> list[DetectedFace]:
        """Detect and embed every face in a BGR uint8 image."""


@runtime_checkable
class TextRecognizer(Protocol):
    def read(self, image_bytes: bytes) -> str:
        """Encoded image bytes (JPEG/PNG) -> recognised text, one line per row."""
