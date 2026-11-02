"""Calibrated semantic image search.

Raw CLIP cosine scores are poorly calibrated: some photos score highly for
*every* query ("hubs") and a fixed threshold either floods you with junk or
hides real matches.  Two gates make results precise:

1. an absolute cosine floor, and
2. a **per-photo contrast test**: the query must describe the photo clearly
   better than a set of generic captions ("a photo", "a blurry photo", ...)
   do.  That is the same softmax CLIP uses for zero-shot classification, with
   generic captions as the competing "classes".

A query that matches nothing therefore returns *nothing* - never the library.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..ml.protocols import ImageEmbedder
from .embeddings import EmbeddingIndex

TEMPLATES = ("a photo of {}", "{}", "a picture showing {}")
BASELINE_CAPTIONS = (
    "a photo", "an image", "a picture", "a snapshot", "a photograph", "a blurry photo",
    "a dark photo", "a bright photo", "a close-up photo", "a wide-angle photo",
    "a photo taken indoors", "a photo taken outdoors", "a photo taken at night",
    "a photo taken during the day", "a candid photo", "a low quality photo",
    "a high quality photo", "a colorful photo", "a black and white photo",
    "a cropped photo", "a vertical photo", "something", "an object", "a scene",
)  # fmt: skip
LOGIT_SCALE = 100.0  # CLIP's learned temperature


@dataclass(frozen=True)
class Threshold:
    cosine_floor: float
    min_probability: float


STRICTNESS: dict[str, Threshold] = {
    "strict": Threshold(0.26, 0.80),
    "balanced": Threshold(0.23, 0.50),
    "broad": Threshold(0.20, 0.20),
}


@dataclass(frozen=True)
class VisualHits:
    ids: np.ndarray  # best match first
    scores: np.ndarray  # cosine similarity, same order
    best_cosine: float  # highest cosine in the whole library (diagnostics)
    considered: int


def _normalize(v: np.ndarray) -> np.ndarray:
    return v / max(float(np.linalg.norm(v)), 1e-9)


class VisualSearch:
    def __init__(self, index: EmbeddingIndex, embedder: ImageEmbedder, strictness: str = "balanced") -> None:
        self._index = index
        self._embedder = embedder
        self.threshold = STRICTNESS.get(strictness, STRICTNESS["balanced"])
        self._baseline: np.ndarray | None = None

    def _baseline_matrix(self) -> np.ndarray:
        if self._baseline is None:
            self._baseline = self._embedder.embed_text(list(BASELINE_CAPTIONS)).astype(np.float32)
        return self._baseline

    def query_vector(self, query: str) -> np.ndarray:
        texts = [t.format(query.strip()) for t in TEMPLATES]
        return _normalize(self._embedder.embed_text(texts).astype(np.float32).mean(axis=0))

    def search(self, query: str) -> VisualHits:
        index = self._index
        if not query.strip() or len(index) == 0:
            return VisualHits(np.zeros(0, np.int64), np.zeros(0, np.float32), 0.0, 0)
        q = self.query_vector(query)
        base = self._baseline_matrix()
        th = self.threshold
        kept_rows: list[np.ndarray] = []
        kept_scores: list[np.ndarray] = []
        best = -1.0
        for start, block in index.chunks():
            cos = block @ q
            best = max(best, float(cos.max()))
            logits_q = LOGIT_SCALE * cos
            logits_b = LOGIT_SCALE * (block @ base.T)
            peak = np.maximum(logits_q, logits_b.max(axis=1))
            num = np.exp(logits_q - peak)
            prob = num / (num + np.exp(logits_b - peak[:, None]).sum(axis=1))
            mask = (cos >= th.cosine_floor) & (prob >= th.min_probability)
            rows = np.nonzero(mask)[0]
            kept_rows.append(rows + start)
            kept_scores.append(cos[rows])
        rows = np.concatenate(kept_rows) if kept_rows else np.zeros(0, np.int64)
        scores = np.concatenate(kept_scores) if kept_scores else np.zeros(0, np.float32)
        order = np.argsort(-scores)
        return VisualHits(index.ids[rows[order]], scores[order], best, len(index))
