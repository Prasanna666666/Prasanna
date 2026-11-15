"""Age of a face in years, from InsightFace's age model (genderage.onnx), run on this Mac.

It reads the small face crops the app already saved, so no original photo is opened. The model returns an age in years (typically within a
few years); the app only uses it for broad groups (baby, child, teenager ...), and only where the estimate sits well inside the group.
"""

from __future__ import annotations

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
