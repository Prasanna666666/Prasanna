"""CLIP embeddings through open_clip on the Apple GPU (PyTorch "mps")."""

from __future__ import annotations

import contextlib
import gc
from pathlib import Path
from typing import Any

import numpy as np


class OpenClipEmbedder:
    """:class:`~aperture.ml.protocols.ImageEmbedder` backed by open_clip."""

    def __init__(self, model: str, pretrained: str, cache_dir: Path) -> None:
        import open_clip  # heavy import kept local so the rest of the app stays light
        import torch

        self._torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model_id = f"{model}/{pretrained}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        net, _, self._preprocess = open_clip.create_model_and_transforms(model, pretrained=pretrained, cache_dir=str(cache_dir))
        self._model = net.eval().to(self.device)
        self._tokenizer = open_clip.get_tokenizer(model)

    def preprocess(self, image: Any) -> Any:
        return self._preprocess(image)

    def embed_prepared(self, prepared: list[Any]) -> np.ndarray:
        torch = self._torch
        with torch.inference_mode():
            feats = self._model.encode_image(torch.stack(prepared).to(self.device))
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.float().cpu().numpy().astype(np.float32)

    def embed_text(self, texts: list[str]) -> np.ndarray:
        torch = self._torch
        with torch.inference_mode():
            tokens = self._tokenizer(texts).to(self.device)
            feats = self._model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.float().cpu().numpy().astype(np.float32)

    def close(self) -> None:
        """Free unified memory - important on an 8 GB machine between passes."""
        self._model = None
        gc.collect()
        with contextlib.suppress(Exception):
            self._torch.mps.empty_cache()
