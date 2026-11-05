"""Shared fixtures: a throw-away 'external drive' and deterministic fake ML."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from images.config import ENV_INTERNAL, Paths
from images.indexing.pipeline import STAGE_FACES, STAGE_INDEX, STAGE_OCR, Services
from images.ml.protocols import DetectedFace
from PIL import Image

from aperture.bootstrap import AppContext

COLOURS = {"red": (220, 20, 20), "blue": (20, 20, 220), "green": (20, 200, 20)}


class FakeEmbedder:
    """Maps a colour word to an axis: red=x, blue=y, anything else=z."""

    model_id = "fake/clip"

    @staticmethod
    def _axis(rgb: np.ndarray) -> np.ndarray:
        v = np.zeros(3, np.float32)
        v[0 if rgb[0] > 150 else 1 if rgb[2] > 150 else 2] = 1.0
        return v

    def preprocess(self, image):
        return np.asarray(image.convert("RGB").resize((4, 4))).reshape(-1, 3).mean(0)

    def embed_prepared(self, prepared):
        return np.vstack([self._axis(p) for p in prepared]).astype(np.float32)

    def embed_text(self, texts):
        out = []
        for t in texts:
            v = np.zeros(3, np.float32)
            v[0 if "red" in t else 1 if "blue" in t else 2] = 1.0
            out.append(v)
        return np.vstack(out)

    def close(self) -> None:
        pass


class FakeFaces:
    """One face per photo; red photos show 'person A', blue photos 'person B'."""

    def analyse(self, bgr):
        blue = float(bgr[..., 0].mean()) > 150  # BGR: channel 0 is blue
        emb = np.zeros(512, np.float32)
        emb[0 if blue else 1] = 1.0
        return [DetectedFace(bbox=(10, 10, 90, 90), score=0.95, embedding=emb)]


class FakeOCR:
    def read(self, image_bytes: bytes) -> str:
        from io import BytesIO

        px = Image.open(BytesIO(image_bytes)).convert("RGB").getpixel((5, 5))
        return "Invoice number 42 Eindhoven" if px[0] > 150 else ""


@pytest.fixture(autouse=True)
def _allow_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_INTERNAL, "1")  # tmp dirs live on the internal disk in CI


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    p = Paths(drive=tmp_path / "drive")
    p.drive.mkdir()
    p.ensure()
    return p


@pytest.fixture
def make_photo() -> Callable[..., Path]:
    def make(folder: Path, name: str, colour: str, size: tuple[int, int] = (120, 100)) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        img = Image.new("RGB", size, COLOURS[colour])
        tag = sum(map(ord, name)) % 200 + 20  # make every photo's bytes unique
        img.paste((tag, tag, tag), (size[0] - 16, size[1] - 16, size[0], size[1]))
        img.save(target, "JPEG")
        return target

    return make


@pytest.fixture
def library(paths: Paths, make_photo) -> Path:
    root = paths.drive / "Photos"
    for i in range(3):
        make_photo(root / "Holidays" / "Italy", f"red_{i}.jpg", "red")
    for i in range(2):
        make_photo(root / "Family", f"blue_{i}.jpg", "blue")
    return root


@pytest.fixture
def ctx(paths: Paths, library: Path) -> AppContext:
    context = AppContext(paths)
    context.settings.photo_dir = str(library)
    context.settings.export_dir = str(paths.drive / "Export")
    context.settings.workers = 2
    context.settings.save(paths)
    return context


def fake_services(stage: str) -> Services:
    if stage == STAGE_INDEX:
        return Services(embedder=FakeEmbedder())
    if stage == STAGE_FACES:
        return Services(faces=FakeFaces())
    if stage == STAGE_OCR:
        return Services(ocr=FakeOCR())
    return Services()


@pytest.fixture
def scanned(ctx: AppContext) -> AppContext:
    from images.indexing.runner import Scanner

    summary = Scanner(ctx.paths, ctx.settings, ctx.db, fake_services).run()
    assert summary.state == "done", summary
    ctx._embedder = FakeEmbedder()
    return ctx


@pytest.fixture(autouse=True)
def _never_start_the_real_ai_engine(monkeypatch):
    """No test may start Ollama or wait for it: starting the app is faked everywhere."""
    monkeypatch.setattr("aperture.launcher.ensure_ollama", lambda wait=45.0: True)
