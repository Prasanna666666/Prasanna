"""Reading one file into the plain shape: every type of file the parser knows, one at a time, in a sealed subprocess."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from . import limits, readers, sniff

SCHEMA = 1


MAX_BYTES = limits.get("max_file_bytes")


MBOX_MAX_BYTES = 64 * 1024 * 1024 * 1024  # a whole mailbox export can be large; each message inside is still capped


MAX_PAGES = limits.get("max_pages")


MAX_CSV_ROWS = limits.get("max_csv_rows")


MAX_DATA_ROWS = limits.get("max_rows")  # structured rows/lines kept for statements


MAX_CELL = limits.get("max_cell_chars")
MAX_COLUMNS = limits.get("max_columns")
DATA_LINE_CHARS = limits.get("data_line_chars")


TIMEOUT_S = 300  # scanned PDFs are read with OCR, which takes a while


SKIP_NAMES = {"passwords.txt", ".passwords"}  # the passwords for protected PDFs live here: never read as a document


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MIN_SAMPLE_LINES = 2  # a delimited text needs at least this many lines to be recognised
MIN_COLUMNS = 2  # a delimited line has at least this many separators


def clean(text: str) -> str:
    return _CTRL.sub("", text)[: limits.get("max_text_chars")]


def _read_text(path: Path) -> dict:
    text = sniff.decode_text(path.read_bytes()[: 20 * 1024 * 1024]) or path.read_text(encoding="utf-8", errors="replace")
    data: dict = {"lines": [clean(x)[:DATA_LINE_CHARS] for x in text.splitlines()[:MAX_DATA_ROWS]]}
    rows = _delimited_rows(text)  # a plain tab- or semicolon-separated export (some banks give these with no header row)
    if rows:
        data["rows"] = rows
    return {"kind": "text", "text": clean(text), "meta": {}, "data": data}


def _read_csv(path: Path) -> dict:
    head = path.read_bytes()[:4096].decode("utf-8", "replace")
    delimiter = max((",", ";", "\t"), key=head.split("\n")[0].count)  # Dutch banks export with ; or tab
    meta: dict = {}
    rows: list[list[str]] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        for i, row in enumerate(csv.reader(f, delimiter=delimiter)):
            if i >= MAX_CSV_ROWS:
                meta["truncated"] = True
                break
            rows.append(row)
    meta["rows"] = len(rows)
    meta["columns"] = [clean(c)[:80] for c in rows[0]][:50] if rows else []
    text = "\n".join(" | ".join(r) for r in rows)
    return {"kind": "csv", "text": clean(text), "meta": meta, "data": {"rows": [[clean(c)[:MAX_CELL] for c in r][:MAX_COLUMNS] for r in rows[:MAX_DATA_ROWS]]}}


def _is_emlx(path: Path) -> bool:
    return path.suffix.lower() == ".emlx" or sniff.is_emlx(sniff.head_of(path))


def _read_email(path: Path) -> dict:
    return (readers.read_emlx(path) if _is_emlx(path) else readers.read_eml(path))[0]


# One reader per kind of content (see sniff.py: what a file is is judged from its contents, never from a list of allowed endings; a file no reader fits gives the words it
# holds). A new kind of content is a new function here: nothing else changes. Each returns the same shape
# ({kind, text, meta, data}); a picture comes back with the text OCR found in it, which is how the service later tells a photographed receipt from a holiday photo.
PARSERS: dict[str, Callable[[Path], dict]] = {
    "text": _read_text,
    "csv": _read_csv,
    "pdf": lambda path: readers.read_pdf(path, load_passwords()),
    "image": readers.read_image,
    "sheet": readers.read_sheet,
    "doc": readers.read_document,
    "html": readers.read_html,
    "email": _read_email,
    "json": readers.read_json,
    "binary": readers.read_binary,
    "zip": readers.read_binary,  # a package met deeper than the reader opens packages: the words in it
}


def extract(path: Path) -> dict:
    """In-process extraction with the reader for this kind of file. Called only inside the limited subprocess (or by tests). The result records which limits cut something out of it and the
    version of the limits it was read under, and which text recognition read its scanned pages, so that a change of limits (or a better engine) finds what must be read again."""
    res = PARSERS[sniff.kind_of(path)](path)
    meta = res.setdefault("meta", {}) if isinstance(res.get("meta", {}), dict) else {}
    data = res.get("data") or {}
    hit = []
    if meta.get("ocr_cut_short"):
        hit.append("ocr")
    if len(res.get("text", "")) >= limits.get("max_text_chars"):
        hit.append("text")
    if any(isinstance(data.get(k), list) and len(data[k]) >= readers.MAX_ROWS for k in ("lines", "table", "rows")):
        hit.append("rows")
    meta["limits_hit"], meta["limits_version"] = hit, limits.version()
    if meta.get("ocr_pages"):
        meta["ocr_engine"] = readers.ocr_engine_used()
    return res


_table_lines = readers.table_lines


_visual_lines = readers.visual_lines


def load_passwords() -> list[str]:
    """Passwords for protected PDFs: one per line in passwords.txt (in your inbox, or the file named by ATLAS_PASSWORDS_FILE). Never stored."""
    candidates = [os.environ.get("ATLAS_PASSWORDS_FILE", "")] + [
        str(Path(os.environ.get(k, "")) / "passwords.txt") for k in ("ATLAS_INBOX",) if os.environ.get(k)
    ]
    for c in candidates:
        if c and Path(c).is_file():
            try:
                return [ln.strip() for ln in Path(c).read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()][:50]
            except OSError:
                pass
    return []


def _delimited_rows(text: str) -> list[list[str]]:
    """Rows of a plain delimited text file, or [] if it does not look like one (the first lines must split into the same number of columns)."""
    head = [ln for ln in text.splitlines()[:8] if ln.strip()]
    if len(head) < MIN_SAMPLE_LINES:
        return []
    for delimiter in ("\t", ";", ","):
        counts = {ln.count(delimiter) for ln in head[:5]}
        if len(counts) == 1 and counts != {0} and next(iter(counts)) >= MIN_COLUMNS:
            reader = csv.reader(text.splitlines(), delimiter=delimiter)
            return [[clean(c)[:MAX_CELL] for c in r][:MAX_COLUMNS] for _, r in zip(range(MAX_DATA_ROWS), reader, strict=False)]
    return []


def _limits() -> None:  # runs in the child before exec (Linux/macOS)
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def extract_isolated(path: Path, timeout: int = TIMEOUT_S) -> dict:
    r = subprocess.run([sys.executable, "-I", "-m", "library.parser", "--extract-one", str(path)], capture_output=True, timeout=timeout, check=False)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:] or f"parser exited {r.returncode}")
    return json.loads(r.stdout)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
