"""Paths, user settings and process environment.

Nothing in this module touches the disk at import time, and there is no global
mutable state: callers build a :class:`Paths` (usually via :func:`default_paths`)
and pass it around.  That keeps every other module trivially testable with a
temporary directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

DEFAULT_DRIVE = Path("/Volumes/Expansion")
ENV_DRIVE = "APERTURE_DRIVE"
ENV_ONLINE = "APERTURE_ALLOW_NETWORK"  # set to "1" only while fetching models
ENV_INTERNAL = "APERTURE_ALLOW_INTERNAL"  # test escape hatch: allow a non-external drive

STRICTNESS_LEVELS = ("strict", "balanced", "broad")


@dataclass(frozen=True)
class Paths:
    """Every location Aperture writes to, derived from the external drive."""

    drive: Path

    @property
    def root(self) -> Path:
        return self.drive / "Aperture"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def jobs(self) -> Path:
        return self.data / "jobs"

    @property
    def geo(self) -> Path:
        return self.data / "geo"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def db(self) -> Path:
        return self.data / "aperture.db"

    @property
    def settings_file(self) -> Path:
        return self.data / "settings.json"

    @property
    def progress_file(self) -> Path:
        return self.data / "progress.json"

    @property
    def scan_pid(self) -> Path:
        return self.data / "scan.pid"

    @property
    def face_models(self) -> Path:
        return self.models / "buffalo_l"

    @property
    def clip_cache(self) -> Path:
        return self.models / "openclip"

    def ensure(self) -> None:
        """Create the directory tree (call only after the drive was validated)."""
        for p in (self.data, self.models, self.logs, self.jobs, self.geo, self.tmp, self.cache):
            p.mkdir(parents=True, exist_ok=True)


def default_paths() -> Paths:
    return Paths(Path(os.environ.get(ENV_DRIVE, str(DEFAULT_DRIVE))))


def online_allowed() -> bool:
    return os.environ.get(ENV_ONLINE) == "1"


def thumb_rel(item_id: int) -> str:
    """Thumbnail path relative to ``Paths.data`` (sharded to keep folders small)."""
    return f"thumbs/{item_id // 1000:04d}/{item_id}.jpg"


def preview_rel(item_id: int) -> str:
    return f"previews/{item_id // 1000:04d}/{item_id}.jpg"


def face_rel(face_id: int) -> str:
    return f"faces/{face_id // 1000:04d}/{face_id}.jpg"


@dataclass
class Stages:
    """Which indexing passes run.  Metadata/thumbnails always run."""

    clip: bool = True
    faces: bool = True
    ocr: bool = True


DENSITY_COLUMNS = {"compact": 8, "comfortable": 6, "spacious": 4}


@dataclass
class Settings:
    """User-tunable settings persisted as JSON on the external drive."""

    photo_dir: str = ""
    export_dir: str = ""
    auto_scan: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    vision_model: str = "llava:7b"  # checks retrieved photos; optional
    agentic: bool = True  # tool-using agent loop (False = single-shot planner)
    agent_max_steps: int = 8
    verify_limit: int = 40  # most photos the vision model re-checks in one step
    clip_model: str = "ViT-B-32"
    clip_pretrained: str = "laion2b_s34b_b79k"
    visual_strictness: str = "balanced"
    page_size: int = 36
    ui_density: str = "comfortable"  # compact | comfortable | spacious (photos per row)
    high_contrast: bool = False
    thumb_size: int = 360
    preview_size: int = 1600
    ocr_max_side: int = 3200
    ocr_max_pdf_pages: int = 60
    batch_size: int = 16
    workers: int = 3
    face_det_size: int = 640
    face_det_thresh: float = 0.5
    face_min_score: float = 0.6
    face_min_px: int = 40
    face_use_coreml: bool = False
    cluster_threshold: float = 0.40
    export_verify: bool = True
    allow_moves: bool = True  # moves still need an explicit preview and confirm for every batch
    move_dir: str = ""  # where moved duplicates go (inside the photo folder)
    stages: Stages = field(default_factory=Stages)

    # -- construction -----------------------------------------------------
    @classmethod
    def defaults(cls, paths: Paths) -> Settings:
        return cls(
            photo_dir=str(paths.drive / "Photos"),
            export_dir=str(paths.drive / "Aperture_Exports"),
        )

    @classmethod
    def load(cls, paths: Paths) -> Settings:
        """Defaults overlaid with the saved file.  Never raises: unreadable or
        wrongly-typed values silently fall back to their defaults."""
        settings = cls.defaults(paths)
        try:
            raw = json.loads(paths.settings_file.read_text())
        except (OSError, ValueError):
            return settings.normalized()
        if isinstance(raw, dict):
            _overlay(settings, raw)
        return settings.normalized()

    def save(self, paths: Paths) -> None:
        paths.data.mkdir(parents=True, exist_ok=True)
        tmp = paths.settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(_to_dict(self.normalized()), indent=2))
        os.replace(tmp, paths.settings_file)

    # -- validation -------------------------------------------------------
    def normalized(self) -> Settings:
        """Return a copy with every numeric value clamped to a safe range."""
        s = Settings(**{f.name: getattr(self, f.name) for f in fields(self)})
        s.stages = Stages(**_to_dict(self.stages))
        if s.visual_strictness not in STRICTNESS_LEVELS:
            s.visual_strictness = "balanced"
        s.page_size = _clamp(s.page_size, 6, 200)
        if s.ui_density not in DENSITY_COLUMNS:
            s.ui_density = "comfortable"
        s.thumb_size = _clamp(s.thumb_size, 120, 1024)
        s.preview_size = _clamp(s.preview_size, 640, 4096)
        s.ocr_max_side = _clamp(s.ocr_max_side, 1024, 6000)
        s.ocr_max_pdf_pages = _clamp(s.ocr_max_pdf_pages, 1, 500)
        s.batch_size = _clamp(s.batch_size, 1, 64)
        s.workers = _clamp(s.workers, 1, 8)
        s.face_det_size = _clamp(s.face_det_size // 32 * 32, 320, 1280)
        s.face_det_thresh = _clamp(s.face_det_thresh, 0.1, 0.95)
        s.face_min_score = _clamp(s.face_min_score, 0.1, 0.99)
        s.face_min_px = _clamp(s.face_min_px, 8, 400)
        s.cluster_threshold = _clamp(s.cluster_threshold, 0.2, 0.8)
        return s


def _clamp(value: Any, low: Any, high: Any) -> Any:
    return max(low, min(high, value))


def _to_dict(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields(obj):
        v = getattr(obj, f.name)
        out[f.name] = _to_dict(v) if is_dataclass(v) else v
    return out


def _overlay(target: Any, raw: dict[str, Any]) -> None:
    """Copy values from ``raw`` onto ``target`` when key and type both fit."""
    for f in fields(target):
        if f.name not in raw:
            continue
        current, value = getattr(target, f.name), raw[f.name]
        if is_dataclass(current) and isinstance(value, dict):
            _overlay(current, value)
        elif isinstance(current, bool):
            if isinstance(value, bool):
                setattr(target, f.name, value)
        elif isinstance(current, float):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                setattr(target, f.name, float(value))
        elif isinstance(current, int):
            if isinstance(value, int) and not isinstance(value, bool):
                setattr(target, f.name, value)
        elif isinstance(current, str) and isinstance(value, str):
            setattr(target, f.name, value)


def configure_environment(paths: Paths, *, online: bool = False) -> None:
    """Keep every cache and temp file on the external drive and force the ML
    libraries into offline mode.  Call this *before* importing torch/open_clip."""
    env = os.environ
    env.setdefault("HF_HOME", str(paths.models / "hf"))
    env.setdefault("TORCH_HOME", str(paths.models / "torch"))
    env.setdefault("MPLCONFIGDIR", str(paths.cache / "mpl"))
    env.setdefault("TMPDIR", str(paths.tmp))
    env.setdefault("PYTHONPYCACHEPREFIX", str(paths.cache / "pycache"))
    env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    env.setdefault("DO_NOT_TRACK", "1")
    env.setdefault("ANONYMIZED_TELEMETRY", "False")
    if not online:
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
            env[key] = "1"
