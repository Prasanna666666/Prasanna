"""Draws the app icon (no image files to ship) and packs it into a macOS .icns."""

from __future__ import annotations

import itertools
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
STOPS = [(0.0, (79, 70, 229)), (0.45, (139, 92, 246)), (0.75, (236, 72, 153)), (1.0, (251, 146, 60))]


def _gradient(size: int) -> Image.Image:
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    t = (xx + yy) / (2 * (size - 1))
    out = np.zeros((size, size, 3), np.float32)
    for (t0, c0), (t1, c1) in itertools.pairwise(STOPS):
        mask = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[mask][:, None]
        out[mask] = np.array(c0) * (1 - f) + np.array(c1) * f
    return Image.fromarray(out.astype(np.uint8), "RGB")


def render(size: int = SIZE) -> Image.Image:
    """A soft gradient tile with a six-blade iris: a camera lens that also reads as a flower."""
    s = size * 2  # draw at 2x, then downsample for smooth edges
    base = _gradient(s).convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((s * 0.05, s * 0.05, s * 0.95, s * 0.95), radius=s * 0.22, fill=255)
    base.putalpha(mask)

    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = cy = s / 2
    for k in range(6):  # petals: rotated ellipses give the iris its overlapping look
        petal = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        pd = ImageDraw.Draw(petal)
        pd.ellipse((cx - s * 0.075, cy - s * 0.33, cx + s * 0.075, cy - s * 0.02), fill=(255, 255, 255, 120))
        layer = Image.alpha_composite(layer, petal.rotate(k * 60, center=(cx, cy), resample=Image.BICUBIC))
    d = ImageDraw.Draw(layer)
    r = s * 0.075
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    ring = s * 0.36
    d.ellipse((cx - ring, cy - ring, cx + ring, cy + ring), outline=(255, 255, 255, 235), width=int(s * 0.022))
    glow = layer.filter(ImageFilter.GaussianBlur(s * 0.012))
    base = Image.alpha_composite(base, glow)
    base = Image.alpha_composite(base, layer)
    return base.resize((size, size), Image.LANCZOS)


def write_icns(destination: Path) -> bool:
    """Build ``destination`` (.icns) with macOS ``iconutil``.  Returns False if unavailable."""
    if not shutil.which("iconutil"):
        return False
    art = render()
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            art.resize((base, base), Image.LANCZOS).save(iconset / f"icon_{base}x{base}.png")
            art.resize((base * 2, base * 2), Image.LANCZOS).save(iconset / f"icon_{base}x{base}@2x.png")
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(destination)], check=False)
    return result.returncode == 0 and destination.is_file()


if __name__ == "__main__":  # pragma: no cover - manual preview
    render(512).save("icon_preview.png")
