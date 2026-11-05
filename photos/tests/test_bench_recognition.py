"""The recognition benchmark runs on a Mac with real models; its logic is checked here with fakes (no photos, no models)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

SCRIPT = Path(__file__).parent.parent / "scripts" / "bench-recognition.py"
spec = importlib.util.spec_from_file_location("bench_rec", SCRIPT)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class FakeEmbedder:
    device = "fake"

    def __init__(self):
        self.calls = []

    def preprocess(self, image):
        return np.zeros((3, 4, 4), dtype=np.float32)

    def embed_prepared(self, prepared):
        self.calls.append(len(prepared))
        return np.zeros((len(prepared), 8), dtype=np.float32)


class FakeFaces:
    def analyse(self, bgr):
        assert bgr.ndim == 3 and bgr.flags["C_CONTIGUOUS"]
        return [object(), object()]


def loader(path, max_side):
    return Image.new("RGB", (64, 48)), None


def test_run_measures_every_stage_and_batch_size():
    emb = FakeEmbedder()
    res = bench.run(emb, FakeFaces(), [Path(f"p{i}.jpg") for i in range(10)], loader, batch_sizes=(2, 5), rss=lambda: 123.0)
    assert res["photos"] == 10 and res["faces_found"] == 20
    assert set(res["clip_img_per_s"]) == {2, 5} and all(v > 0 for v in res["clip_img_per_s"].values())
    assert 1 in emb.calls and 2 in emb.calls and 5 in emb.calls  # warm-up of 1, then the two batch sizes
    assert res["rss_after_clip_mb"] == 123.0


def test_run_works_without_clip_or_faces():
    res = bench.run(None, None, [Path("a.jpg")], loader, rss=lambda: 1.0)
    assert "clip_img_per_s" not in res and "faces_s_per_photo" not in res and res["decode_s_per_photo"] >= 0


def test_estimate_and_report_are_readable():
    res = {
        "photos": 8,
        "decode_s_per_photo": 0.1,
        "rss_after_decode_mb": 400,
        "clip_img_per_s": {4: 20.0, 8: 30.0},
        "rss_after_clip_mb": 1500,
        "faces_s_per_photo": 0.2,
        "faces_found": 11,
        "rss_after_faces_mb": 1700,
    }
    est = bench.estimate_hours(res, 36000, workers=2)
    assert est["clip"] == pytest.approx(36000 / 30 / 3600) and est["faces"] == pytest.approx(2.0)
    text = bench.report(res, 36000)
    assert "batch 8: 30.0 img/s" in text and "36,000 photos" in text and "faces:" in text


def test_no_photos_message(tmp_path, capsys):
    assert bench.main([str(tmp_path)]) == 2
    assert "No photos found" in capsys.readouterr().out
