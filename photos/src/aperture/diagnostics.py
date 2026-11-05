"""Health checks shown in Settings and used by ``aperture doctor``-style views."""

from __future__ import annotations

import os
from dataclasses import dataclass

from images.ml.ocr import text_available
from images.safety import drive_problem

from .agent.llm import LLMError
from .bootstrap import AppContext


@dataclass(frozen=True)
class Check:
    ok: bool
    label: str
    detail: str
    required: bool = True


def run_checks(ctx: AppContext) -> list[Check]:
    s, p = ctx.settings, ctx.paths
    checks = [Check(not (problem := drive_problem(p.drive)), "External drive", problem or str(p.drive))]
    checks.append(Check(bool(s.photo_dir) and os.path.isdir(s.photo_dir), "Photo folder", s.photo_dir or "not chosen yet"))
    checks.append(Check(bool(s.export_dir), "Export folder", s.export_dir or "not chosen yet", required=False))
    try:
        models = ctx.llm().list_models()
    except LLMError as exc:
        models, error = [], str(exc)
    else:
        error = ""

    def has(name: str) -> bool:
        return name in models or f"{name}:latest" in models

    checks.append(
        Check(
            has(s.ollama_model),
            f"AI model ({s.ollama_model})",
            error or ("ready" if has(s.ollama_model) else f"run: ollama pull {s.ollama_model}"),
        )
    )
    checks.append(
        Check(
            has(s.vision_model),
            f"Vision model ({s.vision_model})",
            error or ("ready" if has(s.vision_model) else f"optional, for double-checking results: ollama pull {s.vision_model}"),
            required=False,
        )
    )
    faces = all((p.face_models / f).exists() for f in ("det_10g.onnx", "w600k_r50.onnx"))
    checks.append(Check(faces, "Face models", "ready" if faces else "run: aperture fetch-models"))
    geo = (p.geo / "cities15000.txt").exists()
    checks.append(Check(geo, "Place data", "ready" if geo else "run: aperture fetch-models", required=False))
    checks.append(
        Check(
            text_available(),
            "Text recognition",
            "ready" if text_available() else "needs Apple Vision or Tesseract",
            required=False,
        )
    )
    return checks
