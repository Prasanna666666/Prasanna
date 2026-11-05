"""One reader for every kind of file: PDF (text or scanned), images, spreadsheets, Word, web pages, emails, JSON, archives.

Everything comes out in the SAME shape, which is all the rest of the app (and the local model) ever sees:
    {"kind": ..., "text": plain text, "meta": {...}, "data": {"table": [[ [x0, x1, text], ... ], ...]  # lines of cells with positions (PDF, scans, images)
                                                               "rows":  [[cell, ...], ...]             # a plain grid (spreadsheets, CSV, tables)
                                                               "lines": [text, ...]}}                  # one text line each
Scanned pages and images are read with Tesseract (offline, Dutch + English) and give the same positioned cells as a text PDF, so a scanned statement
goes through exactly the same layout reading and the same proofs. OCR can misread a digit; the balance checks are what catch that.
This runs only inside the parser container (no network); everything here is bounded.
"""

from __future__ import annotations

import email
import email.policy
import io
import json
import math
import re
import shutil
import subprocess
import zipfile
from datetime import date, datetime
from functools import lru_cache
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from . import log

MAX_ROWS = 50_000
MAX_CELL = 300
OCR_DPI = 250
MAX_OCR_PAGES = 60
ZIP_MAX_ENTRIES = 200
ZIP_MAX_TOTAL = 200 * 1024 * 1024
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str, limit: int = 2_000_000) -> str:
    return _CTRL.sub("", text)[:limit]


# ---- lines and cells from positioned words ----------------------------------------------------------------------------------
def table_lines(words: list, gap: float = 7.0) -> list[list[list]]:
    """Lines as cells: [[x0, x1, text], ...]. Words on one line closer than `gap` points are one cell; a wider gap starts a new cell."""
    items = sorted(((round((w[1] + w[3]) / 2), w[0], w[2], clean(str(w[4]))) for w in words if str(w[4]).strip()), key=lambda t: (t[0], t[1]))
    lines: list[list[tuple[float, float, str]]] = []
    last_y = None
    for y, x0, x1, text in items:
        if last_y is None or abs(y - last_y) > 3:
            lines.append([])
            last_y = y
        lines[-1].append((x0, x1, text))
    out = []
    for line in lines:
        line.sort()
        cells: list[list] = []
        for x0, x1, text in line:
            if cells and x0 - cells[-1][1] < gap:
                cells[-1][1], cells[-1][2] = max(cells[-1][1], x1), cells[-1][2] + " " + text
            else:
                cells.append([round(x0, 1), round(x1, 1), text])
        out.append([[c[0], c[1], c[2][:200]] for c in cells])
    return out


def visual_lines(words: list) -> list[str]:
    return [" ".join(c[2] for c in line) for line in table_lines(words, gap=1e9)]


# ---- OCR --------------------------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def ocr_languages() -> str:
    """Dutch + English if installed, else whatever English-capable pack exists; '' if Tesseract is missing."""
    exe = shutil.which("tesseract")
    if not exe:
        return ""
    try:
        listed = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=20, check=False).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    wanted = [lang for lang in ("nld", "eng") if lang in listed]
    return "+".join(wanted) or ("eng" if "eng" in listed else "")


def run_tesseract(png: bytes) -> str:
    """Tesseract's TSV (word boxes) for one page image. Replaced in tests."""
    langs = ocr_languages()
    if not langs:
        raise RuntimeError("Tesseract is not installed in the parser image")
    done = subprocess.run(["tesseract", "stdin", "stdout", "-l", langs, "--psm", "6", "tsv"], input=png, capture_output=True, timeout=180, check=False)
    if done.returncode != 0:
        raise RuntimeError("Tesseract failed on a page")
    return done.stdout.decode("utf-8", "replace")


def ocr_words(png: bytes, scale: float) -> tuple[list[tuple], float]:
    """(words as (x0, y0, x1, y1, text) in the page's own units, mean confidence) from one page image. `scale` = pixels per page unit."""
    words, confs = [], []
    for line in run_tesseract(png).splitlines()[1:]:
        p = line.split("\t")
        if len(p) < 12 or not p[11].strip():
            continue
        try:
            left, top, w, h, conf = float(p[6]), float(p[7]), float(p[8]), float(p[9]), float(p[10])
        except ValueError:
            continue
        if conf < 0:
            continue
        words.append((left / scale, top / scale, (left + w) / scale, (top + h) / scale, p[11].strip()))
        confs.append(conf)
    return words, (sum(confs) / len(confs) if confs else 0.0)


# ---- PDF (text, scanned, password-protected) ---------------------------------------------------------------------------------
def read_pdf(path: Path, passwords: list[str] | None = None) -> dict:
    import pymupdf

    meta: dict = {}
    pages_text: list[str] = []
    table: list = []
    lines: list[str] = []
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            if not any(doc.authenticate(p) for p in [*(passwords or []), ""]):
                raise ValueError("this PDF is password-protected: put its password in passwords.txt in your finance folder (one per line)")
            meta["unlocked"] = True
        meta["pages"] = doc.page_count
        ocr_pages, confs = 0, []
        for i in range(min(doc.page_count, 500)):
            page = doc[i]
            words = page.get_text("words")
            text = page.get_text()
            if len(words) < 3 and ocr_pages < MAX_OCR_PAGES:  # no text layer: a scan. Read it.
                pix = page.get_pixmap(dpi=OCR_DPI)
                words, conf = ocr_words(pix.tobytes("png"), OCR_DPI / 72)
                text = "\n".join(visual_lines(words))
                ocr_pages += 1
                confs.append(conf)
            pages_text.append(text)
            lines += visual_lines(words)
            table += table_lines(words)
        if ocr_pages:
            meta["ocr_pages"] = ocr_pages
            meta["ocr_confidence"] = round(sum(confs) / len(confs), 1) if confs else 0.0
    data = {"lines": [clean(x, 600) for x in lines[:MAX_ROWS]], "table": table[:MAX_ROWS]}
    if not meta.get("ocr_pages"):  # a real text layer: read it with other, independent engines too, so the readings can be compared
        for engine, alt in other_engines(path, passwords, min(meta["pages"], 500)).items():
            data[f"table_{engine}"] = alt[:MAX_ROWS]
            meta.setdefault("engines", []).append(engine)
    return {"kind": "pdf", "text": clean("\n\n".join(pages_text)), "meta": meta, "data": data}


def _pdfplumber_pages(path: Path, passwords: list[str], pages: int) -> list[list[tuple]]:
    import pdfplumber

    for pw in [*passwords, ""]:
        try:
            with pdfplumber.open(path, password=pw or None) as pdf:
                return [[(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in page.extract_words()] for page in pdf.pages[:pages]]
        except Exception as exc:  # noqa: BLE001 - pdfplumber raises many kinds of error for a wrong password or a damaged file: try the next password
            last = exc
    raise last


_BBOX_PAGE = re.compile(r"<page\b.*?</page>", re.DOTALL)
_BBOX_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', re.DOTALL)


def _poppler_pages(path: Path, passwords: list[str], pages: int) -> list[list[tuple]]:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("poppler is not installed")
    for pw in [*passwords, ""]:
        cmd = [exe, "-bbox", "-l", str(pages), *(["-upw", pw] if pw else []), str(path), "-"]
        done = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        if done.returncode == 0:
            html = done.stdout.decode("utf-8", "replace")
            return [[(float(a), float(b), float(c), float(d), unescape(t)) for a, b, c, d, t in _BBOX_WORD.findall(page)] for page in _BBOX_PAGE.findall(html)]
    raise RuntimeError("poppler could not open the file")


def other_engines(path: Path, passwords: list[str] | None, pages: int) -> dict[str, list]:
    """The same pages read by other PDF engines (pdfminer via pdfplumber, and poppler): each as a table, like the main reading. An engine that fails is simply absent."""
    out = {}
    for name, read in (("pdfplumber", _pdfplumber_pages), ("poppler", _poppler_pages)):
        try:
            table: list = []
            for words in read(path, list(passwords or []), pages):
                table += table_lines(words)
            out[name] = table
        except Exception as exc:  # noqa: BLE001 - a second engine failing must never lose the file: it is only a second opinion
            log.failed("extra pdf engine failed", exc, engine=name)
    return out


def read_image(path: Path) -> dict:
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "PNG")
        width = im.width
    words, conf = ocr_words(buf.getvalue(), 1.0)
    table = table_lines(words)
    lines = visual_lines(words)
    return {
        "kind": "image",
        "text": clean("\n".join(lines)),
        "meta": {"ocr_pages": 1, "ocr_confidence": round(conf, 1), "width": width},
        "data": {"lines": [clean(x, 600) for x in lines[:MAX_ROWS]], "table": table[:MAX_ROWS]},
    }


# ---- spreadsheets, Word, web pages, email, JSON ------------------------------------------------------------------------------
def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, float):
        return format(v, "f").rstrip("0").rstrip(".") if not math.isnan(v) else ""
    return clean(str(v), MAX_CELL)


def read_sheet(path: Path) -> dict:
    import openpyxl

    rows: list[list[str]] = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                cells = [_cell(v) for v in r][:60]
                if any(cells):
                    rows.append(cells)
                if len(rows) >= MAX_ROWS:
                    break
            rows.append([])
    finally:
        wb.close()
    rows = [r for r in rows if r] or []
    return {"kind": "sheet", "text": clean("\n".join(" | ".join(r) for r in rows)), "meta": {"rows": len(rows)}, "data": {"rows": rows}}


def _safe_xml(raw: bytes):
    if re.search(rb"<!DOCTYPE|<!ENTITY", raw[:4096], re.IGNORECASE) or len(raw) > 20_000_000:
        raise ValueError("unsafe XML refused")
    return ET.fromstring(raw)


def read_docx(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        info = z.getinfo("word/document.xml")
        if info.file_size > 20_000_000:
            raise ValueError("document too large")
        root = _safe_xml(z.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paras, rows = [], []
    for el in root.iter():
        if el.tag == f"{w}p":
            paras.append("".join(t.text or "" for t in el.iter(f"{w}t")))
        elif el.tag == f"{w}tr":
            rows.append([clean("".join(t.text or "" for t in tc.iter(f"{w}t")), MAX_CELL) for tc in el.iter(f"{w}tc")])
    text = "\n".join(p for p in paras if p.strip())
    return {
        "kind": "doc",
        "text": clean(text),
        "meta": {},
        "data": {"lines": [clean(p, 600) for p in text.splitlines()[:MAX_ROWS]], **({"rows": rows[:MAX_ROWS]} if rows else {})},
    }


class _Html(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
        elif tag in ("br", "p", "div", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._cell is not None:
            self._cell.append(data)


def read_html_text(html: str) -> dict:
    p = _Html()
    p.feed(html[:20_000_000])
    text = "\n".join(" ".join(ln.split()) for ln in "".join(p.parts).splitlines() if ln.strip())
    return {
        "kind": "html",
        "text": clean(text),
        "meta": {},
        "data": {"lines": [clean(x, 600) for x in text.splitlines()[:MAX_ROWS]], **({"rows": p.rows[:MAX_ROWS]} if p.rows else {})},
    }


def read_html(path: Path) -> dict:
    return read_html_text(path.read_text(encoding="utf-8", errors="replace"))


def read_eml(path: Path) -> tuple[dict, list[tuple[str, bytes]]]:
    msg = email.message_from_binary_file(path.open("rb"), policy=email.policy.default)
    body = msg.get_body(preferencelist=("plain", "html"))
    content = body.get_content() if body is not None else ""
    parsed = read_html_text(content) if body is not None and body.get_content_type() == "text/html" else None
    text = parsed["text"] if parsed else clean(content)
    head = f"From: {msg.get('From', '')}\nTo: {msg.get('To', '')}\nDate: {msg.get('Date', '')}\nSubject: {msg.get('Subject', '')}\n"
    attachments = [
        (a.get_filename() or "attachment", a.get_content() if isinstance(a.get_content(), bytes) else str(a.get_content()).encode())
        for a in msg.iter_attachments()
        if a.get_filename()
    ]
    full = clean(head + "\n" + text)
    return {
        "kind": "email",
        "text": full,
        "meta": {"subject": clean(str(msg.get("Subject", "")), 200), "attachments": len(attachments)},
        "data": {"lines": [clean(x, 600) for x in full.splitlines()[:MAX_ROWS]]},
    }, attachments


def read_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    rows: list[list[str]] = []
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        keys = list(dict.fromkeys(k for x in obj[:500] for k in x))[:60]
        rows = [keys] + [[_cell(x.get(k)) for k in keys] for x in obj[:MAX_ROWS]]
    text = json.dumps(obj, ensure_ascii=False, indent=1)
    return {
        "kind": "json",
        "text": clean(text),
        "meta": {},
        "data": {"lines": [clean(x, 600) for x in text.splitlines()[:MAX_ROWS]], **({"rows": rows} if rows else {})},
    }


# ---- archives ----------------------------------------------------------------------------------------------------------------
def zip_members(path: Path) -> list[tuple[str, bytes]]:
    """The files inside a ZIP, bounded: few entries, small total, no paths (only the file name is kept), no archives inside archives."""
    out, total = [], 0
    with zipfile.ZipFile(path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()][:ZIP_MAX_ENTRIES]
        for info in infos:
            name = Path(info.filename).name
            total += info.file_size
            if total > ZIP_MAX_TOTAL or info.file_size > 50 * 1024 * 1024 or name.startswith(".") or name.lower().endswith(".zip"):
                continue
            with z.open(info) as f:
                out.append((name, f.read(info.file_size + 1)[: info.file_size]))
    return out
