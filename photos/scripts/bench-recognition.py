#!/usr/bin/env python3
"""How fast is Aperture's picture recognition on THIS Mac, and how much memory does it use?

    python3 scripts/bench-recognition.py /path/to/a/folder/of/photos           # 32 photos from that folder
    python3 scripts/bench-recognition.py FOLDER --count 64 --library 80000      # also estimate hours for 80,000 photos

Run it from your Aperture virtual environment, with Ollama idle (`ollama stop` any loaded model) so the numbers are fair.
It reads the sample photos (never changes them), prints only numbers - no file names - and writes nothing.

Stages (the same code Aperture uses when it indexes):
  decode   open a photo, honour rotation, make the preview
  clip     the image-search model (open_clip on the Apple GPU), at several batch sizes
  faces    face detection + face embedding (onnxruntime)
Accuracy is a different question: `aperture eval` measures how many of YOUR known photos a search finds or misses.
"""

from __future__ import annotations

import argparse
import resource
import sys
import time
from pathlib import Path

EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def rss_mb() -> float:
    """Peak memory of this process so far (bytes on macOS, KB on Linux)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def run(embedder, faces, paths: list[Path], loader, batch_sizes=(4, 8, 16), preview_size: int = 1600, rss=rss_mb) -> dict:
    """Pure measurement: everything it needs is passed in, so it can be tested without models."""
    out: dict = {"photos": len(paths)}
    t = time.perf_counter()
    previews = []
    for p in paths:
        image, _meta = loader(p, preview_size)
        image = image.copy()
        image.thumbnail((preview_size, preview_size))
        previews.append(image)
    out["decode_s_per_photo"] = (time.perf_counter() - t) / len(paths)
    out["rss_after_decode_mb"] = rss()

    if embedder is not None:
        embedder.embed_prepared([embedder.preprocess(previews[0])])  # warm-up (compilation / first kernel launches)
        clip = {}
        for bs in batch_sizes:
            t = time.perf_counter()
            done = 0
            for i in range(0, len(previews), bs):
                batch = [embedder.preprocess(im) for im in previews[i : i + bs]]
                embedder.embed_prepared(batch)
                done += len(batch)
            clip[bs] = done / (time.perf_counter() - t)
        out["clip_img_per_s"] = clip
        out["rss_after_clip_mb"] = rss()
    if faces is not None:
        import numpy as np

        t = time.perf_counter()
        found = 0
        for im in previews:
            found += len(faces.analyse(np.ascontiguousarray(np.asarray(im)[:, :, ::-1])))
        out["faces_s_per_photo"] = (time.perf_counter() - t) / len(previews)
        out["faces_found"] = found
        out["rss_after_faces_mb"] = rss()
    return out


def estimate_hours(res: dict, library: int, workers: int = 2) -> dict:
    """Rough one-time indexing time. Decode is spread over workers; the GPU and the face model run one at a time."""
    est = {}
    if "decode_s_per_photo" in res:
        est["decode"] = library * res["decode_s_per_photo"] / max(workers, 1) / 3600
    if res.get("clip_img_per_s"):
        est["clip"] = library / max(res["clip_img_per_s"].values()) / 3600
    if "faces_s_per_photo" in res:
        est["faces"] = library * res["faces_s_per_photo"] / 3600
    return est


def report(res: dict, library: int | None) -> str:
    lines = [
        f"photos measured: {res['photos']}",
        f"decode:  {res['decode_s_per_photo'] * 1000:.0f} ms per photo (memory so far {res['rss_after_decode_mb']:.0f} MB)",
    ]
    if "clip_img_per_s" in res:
        lines.append(
            "clip:    "
            + ", ".join(f"batch {b}: {v:.1f} img/s" for b, v in res["clip_img_per_s"].items())
            + f"  (memory {res['rss_after_clip_mb']:.0f} MB)"
        )
    if "faces_s_per_photo" in res:
        lines.append(
            f"faces:   {res['faces_s_per_photo'] * 1000:.0f} ms per photo, {res['faces_found']} faces found "
            f"(memory {res['rss_after_faces_mb']:.0f} MB)"
        )
    if library:
        est = estimate_hours(res, library)
        lines.append(
            f"\nrough one-time indexing time for {library:,} photos (each stage alone): "
            + ", ".join(f"{k} {v:.1f} h" for k, v in est.items())
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure Aperture's recognition speed and memory on this Mac")
    ap.add_argument("folder")
    ap.add_argument("--count", type=int, default=32)
    ap.add_argument("--library", type=int, default=0, help="number of photos in your library, to estimate indexing time")
    a = ap.parse_args(argv)
    paths = sorted(p for p in Path(a.folder).expanduser().rglob("*") if p.suffix.lower() in EXTS and p.is_file())[: a.count]
    if not paths:
        print(f"No photos found in {a.folder}.")
        return 2
    try:
        from images.config import Settings, default_paths
        from images.indexing import loaders
        from images.ml.clip import OpenClipEmbedder
        from images.ml.faces import OnnxFaceAnalyzer
    except ImportError as e:
        print(f"Run this from your Aperture virtual environment ({e}).")
        return 2
    loaders.register_heif()
    paths_, settings = default_paths(), Settings.load(default_paths())
    embedder = faces = None
    try:
        embedder = OpenClipEmbedder(settings.clip_model, settings.clip_pretrained, paths_.clip_cache)
    except Exception as e:
        print(f"(CLIP skipped: {e})")
    try:
        faces = OnnxFaceAnalyzer(
            paths_.face_models,
            det_size=settings.face_det_size,
            det_thresh=settings.face_det_thresh,
            use_coreml=settings.face_use_coreml,
        )
    except Exception as e:
        print(f"(faces skipped: {e})")
    device = getattr(embedder, "device", "n/a")
    print(f"device for image search: {device}; measuring {len(paths)} photos ...", flush=True)
    print(report(run(embedder, faces, paths, loaders.load_image, preview_size=settings.preview_size), a.library or None))
    if embedder is not None:
        embedder.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
