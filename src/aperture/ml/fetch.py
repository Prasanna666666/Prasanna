"""One-off model and data acquisition.

This is the **only** code that may use the network, and only while
``APERTURE_ALLOW_NETWORK=1`` (set by ``aperture fetch-models``).  Before
downloading anything it tries to *import* a copy you already have on this Mac
(e.g. ``~/.insightface`` or the Hugging Face cache), so a machine that already
ran these models needs no download at all.
"""

from __future__ import annotations

import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from ..config import Paths, Settings, online_allowed

BUFFALO_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
COUNTRIES_URL = "https://download.geonames.org/export/dump/countryInfo.txt"
FACE_FILES = ("det_10g.onnx", "w600k_r50.onnx")

Log = Callable[[str], None]


def _hf_cache_name(model_repo: str) -> str:
    return "models--" + model_repo.replace("/", "--")


def import_local_face_models(paths: Paths) -> bool:
    """Copy buffalo_l from ~/.insightface when present (read-only on the source)."""
    source = Path.home() / ".insightface" / "models" / "buffalo_l"
    if not all((source / f).exists() for f in FACE_FILES):
        return False
    paths.face_models.mkdir(parents=True, exist_ok=True)
    for name in FACE_FILES:
        shutil.copy2(source / name, paths.face_models / name)
    return True


def import_local_clip(paths: Paths) -> bool:
    """Copy the default CLIP weights from the Hugging Face cache when present."""
    repo = _hf_cache_name("laion/CLIP-ViT-B-32-laion2B-s34B-b79K")
    for base in (Path.home() / ".cache" / "huggingface" / "hub",):
        src = base / repo
        if src.is_dir():
            shutil.copytree(src, paths.clip_cache / repo, dirs_exist_ok=True)
            return True
    return False


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def fetch_face_models(paths: Paths, log: Log = print) -> None:
    if all((paths.face_models / f).exists() for f in FACE_FILES):
        log("face models: already present")
        return
    if import_local_face_models(paths):
        log("face models: imported from ~/.insightface")
        return
    if not online_allowed():
        raise RuntimeError("Face models missing and network is disabled (run `aperture fetch-models`).")
    log("face models: downloading buffalo_l (~280 MB)...")
    archive = paths.models / "buffalo_l.zip"
    _download(BUFFALO_URL, archive)
    paths.face_models.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for name in FACE_FILES:
            with zf.open(name) as src, open(paths.face_models / name, "wb") as dst:
                shutil.copyfileobj(src, dst)
    archive.unlink(missing_ok=True)


def fetch_clip(paths: Paths, settings: Settings, log: Log = print) -> None:
    import open_clip

    paths.clip_cache.mkdir(parents=True, exist_ok=True)
    if settings.clip_model == "ViT-B-32" and settings.clip_pretrained == "laion2b_s34b_b79k" and import_local_clip(paths):
        log("CLIP: imported from the local Hugging Face cache")
    log(f"CLIP: verifying {settings.clip_model}/{settings.clip_pretrained} ...")
    open_clip.create_model_and_transforms(
        settings.clip_model, pretrained=settings.clip_pretrained, cache_dir=str(paths.clip_cache)
    )
    open_clip.get_tokenizer(settings.clip_model)


def fetch_geo(paths: Paths, log: Log = print) -> None:
    """GeoNames city list: powers offline "photos taken in <city>" search."""
    cities, countries = paths.geo / "cities15000.txt", paths.geo / "countryInfo.txt"
    if cities.exists() and countries.exists():
        log("place data: already present")
        return
    if not online_allowed():
        log("place data: missing (GPS place search disabled until `aperture fetch-models`)")
        return
    log("place data: downloading GeoNames cities (~3 MB)...")
    archive = paths.geo / "cities15000.zip"
    _download(CITIES_URL, archive)
    with zipfile.ZipFile(archive) as zf, zf.open("cities15000.txt") as src, open(cities, "wb") as dst:
        shutil.copyfileobj(src, dst)
    archive.unlink(missing_ok=True)
    _download(COUNTRIES_URL, countries)


def fetch_all(paths: Paths, settings: Settings, log: Log = print) -> None:
    paths.ensure()
    fetch_face_models(paths, log)
    fetch_clip(paths, settings, log)
    fetch_geo(paths, log)
