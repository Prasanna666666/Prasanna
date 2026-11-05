"""Age of a face in years, from InsightFace's age model (genderage.onnx), run on this Mac.

It reads the small face crops the app already saved, so no original photo is opened. The model returns an age in years (typically within a
few years); the app only uses it for broad groups (baby, child, teenager ...), and only where the estimate sits well inside the group.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

CROP_FRACTION = 0.88  # our saved crops have the face at 59% of their width; the model expects 67%: keep the middle 88%


class OnnxAgeEstimator:
    def __init__(self, model_path: Path) -> None:
        import onnxruntime as ort

        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name

    def estimate(self, image: Any) -> float:
        """Age in years for one face crop (a PIL image)."""
        image = image.convert("RGB")
        w, h = image.size
        side = int(min(w, h) * CROP_FRACTION)
        left, top = (w - side) // 2, (h - side) // 2
        image = image.crop((left, top, left + side, top + side)).resize((96, 96))
        blob = np.asarray(image, np.float32).transpose(2, 0, 1)[None]  # RGB, 0..255, the model's own scaling
        out = self._session.run(None, {self._input: blob})[0][0]
        return float(out[2]) * 100.0


# Groups, and the part of each that counts as clearly inside it: an estimate near a boundary gets no label (wrong answers are worse than none).
GROUPS = (
    ("baby", 0, 2),
    ("child", 4, 11),
    ("teenager", 14, 18),
    ("young adult", 22, 32),
    ("adult", 38, 55),
    ("elderly", 65, 120),
)


def age_group(years: float) -> str | None:
    for name, low, high in GROUPS:
        if low <= years <= high:
            return name
    return None
