"""Read-only loading of photos and documents.

Every function here opens originals in *read* mode only.  Decoded pixels are
held in memory and never written back.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..ml.protocols import TextRecognizer
from ..safety import WriteGuard

MAX_TEXT_CHARS = 300_000
_EXIF_DATE = re.compile(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


@dataclass
class FileMeta:
    width: int | None = None
    height: int | None = None
    taken_at: str | None = None
    camera: str | None = None
    lens: str | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


def register_heif() -> None:
    """Teach Pillow to open HEIC/HEIF (iPhone photos) when pillow-heif is installed."""
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass


# --------------------------------------------------------------------------
# EXIF
# --------------------------------------------------------------------------
def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dms_to_degrees(dms: Any, ref: Any) -> float | None:
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    degrees = d + m / 60 + s / 3600
    return -degrees if str(ref).upper() in ("S", "W") else degrees


def _ifd(exif: Any, tag: int) -> dict[Any, Any]:
    try:
        return dict(exif.get_ifd(tag))
    except Exception:
        return {}


def extract_exif(exif: Any) -> FileMeta:
    """Pull the useful fields out of a Pillow ``Exif`` object (never raises)."""
    meta = FileMeta()
    try:
        sub, gps = _ifd(exif, 0x8769), _ifd(exif, 0x8825)
        raw = sub.get(36867) or sub.get(36868) or exif.get(306)
        match = _EXIF_DATE.match(str(raw)) if raw else None
        if match and match.group(1) != "0000":
            meta.taken_at = "{}-{}-{} {}:{}:{}".format(*match.groups())
        make, model = str(exif.get(271, "")).strip(), str(exif.get(272, "")).strip()
        camera = model if model.lower().startswith(make.lower()) else f"{make} {model}"
        meta.camera = camera.strip() or None
        lens = sub.get(0xA434)
        meta.lens = str(lens).strip() or None if lens else None
        if gps.get(2) and gps.get(4):
            meta.gps_lat = _dms_to_degrees(gps.get(2), gps.get(1))
            meta.gps_lon = _dms_to_degrees(gps.get(4), gps.get(3))
        candidates = {
            "iso": sub.get(34855),
            "f_number": _to_float(sub.get(33437)),
            "exposure_s": _to_float(sub.get(33434)),
            "focal_mm": _to_float(sub.get(37386)),
        }
        meta.details = {k: v for k, v in candidates.items() if v is not None}
    except Exception:
        pass
    return meta


def file_date(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------
def load_image(path: str | Path, max_side: int) -> tuple[Any, FileMeta]:
    """Decode once (JPEG draft mode makes this fast), honour EXIF rotation and
    return an RGB image no larger than ``max_side`` plus its metadata."""
    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        width, height = opened.size
        exif = opened.getexif()
        meta = extract_exif(exif)
        orientation = exif.get(0x0112, 1)
        if opened.format == "JPEG":
            opened.draft("RGB", (max_side, max_side))
        opened.load()
        image = ImageOps.exif_transpose(opened).convert("RGB")
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    meta.width, meta.height = width, height
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image, meta


def load_preview(path: Path) -> Any:
    """Open one of Aperture's own preview JPEGs as RGB."""
    from PIL import Image

    with Image.open(path) as opened:
        return opened.convert("RGB")


def jpeg_bytes(image: Any, quality: int = 90) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def save_jpeg(guard: WriteGuard, image: Any, destination: Path, quality: int) -> None:
    """Write a derived image - only ever inside Aperture's own folder."""
    guard.check(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "JPEG", quality=quality)


# --------------------------------------------------------------------------
# PDF and plain text
# --------------------------------------------------------------------------
def load_pdf(
    path: str | Path,
    *,
    recognizer: TextRecognizer | None,
    max_pages: int,
    want_text: bool,
) -> tuple[Any, FileMeta, str]:
    """First page as an image, metadata, and the full text.

    Pages without an embedded text layer are rendered and run through OCR."""
    try:
        import fitz  # PyMuPDF
    except ImportError:  # newer releases expose the same API as `pymupdf`
        import pymupdf as fitz  # type: ignore[no-redef]
    from PIL import Image

    doc = fitz.open(str(path))
    try:
        if doc.needs_pass:
            raise RuntimeError("encrypted PDF")
        info = doc.metadata or {}
        meta = FileMeta(details={"pages": doc.page_count})
        created = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", info.get("creationDate") or "")
        if created:
            y, mo, d, hh, mi, ss = (g or "00" for g in created.groups())
            meta.taken_at = f"{y}-{mo}-{d} {hh}:{mi}:{ss}"
        meta.details.update({k: info[k] for k in ("title", "author") if info.get(k)})
        pages: list[str] = []
        if want_text:
            for number in range(min(doc.page_count, max_pages)):
                page = doc[number]
                text = page.get_text("text") or ""
                if len(text.strip()) < 20 and recognizer is not None:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
                    text = recognizer.read(pixmap.tobytes("png"))
                pages.append(text)
        first = doc[0].get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
        image = Image.open(io.BytesIO(first.tobytes("png"))).convert("RGB")
        meta.width, meta.height = int(doc[0].rect.width), int(doc[0].rect.height)
        return image, meta, "\n\n".join(pages)[:MAX_TEXT_CHARS]
    finally:
        doc.close()


def read_text_file(path: str | Path) -> str:
    return Path(path).read_text(errors="replace")[:MAX_TEXT_CHARS]


def make_text_thumb(name: str, text: str, size: int) -> Any:
    """A simple placeholder picture for .txt/.md files."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (size, int(size * 0.75)), (246, 246, 242))
    draw, font = ImageDraw.Draw(image), ImageFont.load_default()
    draw.text((10, 8), name[:38], fill=(30, 30, 30), font=font)
    for row, line in enumerate(text.splitlines()[:14]):
        draw.text((10, 28 + row * 13), line[:46], fill=(90, 90, 90), font=font)
    return image
