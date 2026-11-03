"""Complete, lossless metadata for every photo, read once and stored for good.

Everything the file says about itself is kept as JSON in ``file_metadata``: every EXIF tag (all IFDs, including GPS and the
camera maker's notes when exiftool is installed), XMP, IPTC, colour profile, container details and file facts, plus a SHA-256
fingerprint. After this pass the original never has to be read again to answer a question about it. Originals are only opened
for reading.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

READER_VERSION = 1
MAX_INLINE_BYTES = 4096  # longer binary values are summarised (length + fingerprint), never silently dropped


def json_safe(value: Any, depth: int = 0) -> Any:
    """Turn any metadata value into something JSON can hold without losing it."""
    if depth > 6:
        return str(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if len(raw) <= MAX_INLINE_BYTES:
            return {"bytes_b64": base64.b64encode(raw).decode()}
        return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if isinstance(value, dict):
        return {str(k): json_safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v, depth + 1) for v in value]
    try:
        return float(value)  # Pillow's rational numbers
    except (TypeError, ValueError):
        return str(value)


def file_facts(path: Path) -> dict[str, Any]:
    stat = path.stat()
    facts: dict[str, Any] = {"name": path.name, "extension": path.suffix.lower(), "bytes": stat.st_size,
                             "modified": stat.st_mtime, "changed": stat.st_ctime}
    birth = getattr(stat, "st_birthtime", None)  # macOS keeps the real creation time
    if birth:
        facts["created"] = birth
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    facts["sha256"] = digest.hexdigest()
    return facts


def pillow_metadata(path: Path) -> dict[str, Any]:
    """Every tag Pillow can see: all EXIF directories with their names, XMP, IPTC, colour profile, container details."""
    from PIL import ExifTags, Image

    out: dict[str, Any] = {}
    with Image.open(path) as image:
        out["format"], out["mode"], out["size"] = image.format, image.mode, list(image.size)
        out["frames"] = getattr(image, "n_frames", 1)
        out["animated"] = bool(getattr(image, "is_animated", False))
        info = {k: v for k, v in image.info.items() if k not in ("exif", "icc_profile", "xmp", "XML:com.adobe.xmp")}
        out["info"] = json_safe(info)
        exif = image.getexif()
        tags: dict[str, Any] = {}
        for tag, value in exif.items():
            tags[ExifTags.TAGS.get(tag, f"Tag{tag:#06x}")] = value
        for name, ifd_id, names in (("Exif", 0x8769, ExifTags.TAGS), ("GPS", 0x8825, ExifTags.GPSTAGS), ("Interop", 0xA005, ExifTags.TAGS)):
            try:
                ifd = exif.get_ifd(ifd_id)
            except Exception:
                continue
            if ifd:
                tags[name] = {names.get(t, f"Tag{t:#06x}"): v for t, v in dict(ifd).items()}
        out["exif"] = json_safe(tags)
        xmp = image.info.get("xmp") or image.info.get("XML:com.adobe.xmp")
        if xmp:
            out["xmp"] = xmp.decode("utf-8", "replace") if isinstance(xmp, (bytes, bytearray)) else str(xmp)
        try:
            from PIL import IptcImagePlugin

            iptc = IptcImagePlugin.getiptcinfo(image)
            if iptc:
                out["iptc"] = json_safe({f"{k[0]}:{k[1]}": v for k, v in iptc.items()})
        except Exception:
            pass
        profile = image.info.get("icc_profile")
        if profile:
            out["icc"] = {"bytes": len(profile), "sha256": hashlib.sha256(profile).hexdigest()}
            try:
                from PIL import ImageCms

                out["icc"]["description"] = ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(__import__("io").BytesIO(profile))).strip()
            except Exception:
                pass
    return out


def exiftool_metadata(path: Path) -> dict[str, Any] | None:
    """The most complete reader there is (maker notes, Live Photo and HDR details, video). Optional: used when installed."""
    exe = shutil.which("exiftool")
    if exe is None:
        return None
    try:
        done = subprocess.run([exe, "-j", "-G1", "-a", "-u", "-n", "-struct", "-api", "largefilesupport=1", str(path)],
                              capture_output=True, text=True, timeout=60, check=False)
        data = json.loads(done.stdout or "[]")
        return json_safe(data[0]) if data else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def read_all(path: str | Path) -> dict[str, Any]:
    """The full record for one file. Each reader is independent: one failing never loses what the others found."""
    path = Path(path)
    record: dict[str, Any] = {"reader_version": READER_VERSION, "read_at": time.time(), "errors": {}}
    for name, reader in (("file", file_facts), ("pillow", pillow_metadata), ("exiftool", exiftool_metadata)):
        try:
            value = reader(path)
            if value is not None:
                record[name] = value
        except Exception as exc:  # unreadable by this reader (not an image, damaged): say so, keep going
            record["errors"][name] = f"{type(exc).__name__}: {exc}"
    return record


def pending(conn: sqlite3.Connection, limit: int = 0) -> list[tuple[int, str]]:
    sql = ("SELECT i.id, i.path FROM items i LEFT JOIN file_metadata m ON m.item_id = i.id "
           "WHERE i.missing=0 AND (m.item_id IS NULL OR m.reader_version < ?) ORDER BY i.id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [(r[0], r[1]) for r in conn.execute(sql, (READER_VERSION,))]


def run(conn: sqlite3.Connection, limit: int = 0, stop: Any = None, report: Callable[[int, int], None] | None = None) -> tuple[int, int]:
    """Read every photo that has no complete record yet. Resumable: commits as it goes. Returns (done, failed)."""
    todo = pending(conn, limit)
    done = failed = 0
    for n, (item_id, path) in enumerate(todo, 1):
        if stop is not None and stop.is_set():
            break
        record = read_all(path) if os.path.exists(path) else {"reader_version": READER_VERSION, "errors": {"file": "missing"}}
        failed += bool(record["errors"]) and not any(k in record for k in ("pillow", "exiftool", "file"))
        conn.execute(
            "INSERT OR REPLACE INTO file_metadata(item_id, reader_version, sha256, data, read_at) VALUES (?,?,?,?,?)",
            (item_id, READER_VERSION, (record.get("file") or {}).get("sha256"), json.dumps(record, ensure_ascii=False), time.time()),
        )
        done += 1
        if n % 100 == 0:
            conn.commit()
            if report:
                report(n, len(todo))
    conn.commit()
    return done, failed
