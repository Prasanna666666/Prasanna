"""What a file really is, judged from its contents. The ending of the name is only a hint, and no list of allowed endings decides whether a file is read: any file
is opened, and the first thing that fits its contents reads it. Only the first few kilobytes and (for packages) the list of names inside are looked at here; nothing is
parsed, so this is safe to do outside the sealed reader."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

HEAD = 8192
IMAGE_STARTS = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"II*\x00", b"MM\x00*", b"BM")
HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"heif", b"avif")
OLE_START = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # old Word, Excel and PowerPoint files
_HEADER_LINE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*: ", re.MULTILINE)
_MAIL_HEADERS = ("received:", "message-id:", "mime-version:", "return-path:", "x-mailer:", "delivered-to:", "content-type:")


def head_of(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(HEAD)


def is_image(head: bytes) -> bool:
    if head.startswith(IMAGE_STARTS) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return True
    return head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS  # iPhone photos


def is_emlx(head: bytes) -> bool:
    """Apple Mail's own message files: a line with the length, then the message."""
    first, _, rest = head.partition(b"\n")
    return first.strip().isdigit() and bool(_HEADER_LINE.match(rest[:200].decode("latin-1")))


def decode_text(raw: bytes) -> str | None:
    """The text in these bytes, or None when they are not text (a NUL, or too many unprintable characters)."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", "replace")
    if raw.count(b"\x00") > max(2, len(raw) // 100):
        return None  # real binary data; a stray NUL in a text file is just dropped below
    raw = raw.replace(b"\x00", b"")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw[:-3].decode("utf-8") if len(raw) > 3 else raw.decode("utf-8")  # a multi-byte character cut by the end of what was read
        except UnicodeDecodeError:
            text = raw.decode("cp1252", "replace")
    printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
    return text if text and printable / len(text) >= 0.9 else None


def _zip_kind(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()[:5000]
            if "word/document.xml" in names:
                return "doc"
            if "xl/workbook.xml" in names:
                return "sheet"
            if any(n.startswith("ppt/slides/") for n in names):
                return "doc"
            if "content.xml" in names and "mimetype" in names and z.read("mimetype")[:60].startswith(b"application/vnd.oasis.opendocument"):
                return "doc"  # LibreOffice and OpenDocument text, spreadsheets and slides
    except (zipfile.BadZipFile, OSError, KeyError, RuntimeError):
        return "binary"
    return "zip"  # any other package: Apple's Pages, Numbers and Keynote, e-books, archives: its members are read one by one


def _text_kind(text: str, path: Path, head: bytes) -> str:
    sample = text.lstrip("﻿ \n\r\t")[:2000]
    lower = sample.lower()
    if lower.startswith(("<!doctype html", "<html")) or "<body" in lower or "<table" in lower[:600]:
        return "html"
    if is_emlx(head) or path.suffix.lower() == ".emlx":  # Apple Mail's own message files are known by their ending as well
        return "email"
    first_lines = "\n".join(sample.splitlines()[:12]).lower()
    if sample.startswith("From ") and ("\nsubject:" in lower or "\nfrom:" in lower):
        return "mbox"
    if (
        _HEADER_LINE.match(sample)
        and any(h in first_lines for h in (*_MAIL_HEADERS, "from:", "subject:", "date:"))
        and len(_HEADER_LINE.findall(sample[:600])) >= 3
    ):
        return "email"
    if sample[:1] in "{[" and path.stat().st_size <= 5_000_000:
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
            return "json"
        except (ValueError, OSError):
            pass
    lines = [ln for ln in sample.splitlines() if ln.strip()][:10]
    hinted = path.suffix.lower() in (".csv", ".tsv")  # the ending only tips the balance: the contents must have delimiters too
    if len(lines) >= 2:
        for delimiter in (",", ";", "\t"):
            counts = [ln.count(delimiter) for ln in lines]
            same = sum(1 for c in counts if c == counts[0]) >= 0.8 * len(counts)
            if counts[0] >= 1 and same and (counts[0] >= 2 or hinted or len(lines) >= 3):
                return "csv"
    return "text"


def kind_of(path: Path) -> str:
    """pdf, image, sheet, doc, html, email, json, csv, text, mbox, zip (a package of other files), or binary (anything else)."""
    head = head_of(path)
    if b"%PDF-" in head[:1024]:  # the header may follow a few stray bytes (a newline, a byte-order mark): many bank statements are like that
        return "pdf"
    if head[:2] == b"PK":
        return _zip_kind(path)
    if head.lstrip()[:5] == b"{\\rtf":
        return "doc"
    if is_image(head):
        return "image"
    if head.startswith(OLE_START):
        return "binary"
    text = decode_text(head)
    if text is not None:
        return _text_kind(text, path, head)
    return "binary"
