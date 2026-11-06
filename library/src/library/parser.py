"""The isolated parser: turns untrusted files (PDF incl. scans, images, spreadsheets, Word, web pages, emails, JSON, ZIP, CSV, text) into one plain JSON shape. It is the only code that opens them.

Runs in its own container with NO network, the inbox mounted read-only, and a single writable output folder that the
app mounts read-only. Each file is parsed in a throw-away subprocess with CPU, memory and time limits, so a hostile or
broken file can at worst fail that one file. Output is JSON only (never pickle), text capped and stripped of control
characters; the app still treats it as untrusted data.

    library-parser --once  [--inbox /inbox --out /parsed]
    library-parser --watch
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import readers

SCHEMA = 1
MAX_BYTES = 50 * 1024 * 1024
MBOX_MAX_BYTES = 4 * 1024 * 1024 * 1024  # a whole mailbox export can be large; each message inside is still capped
MAX_TEXT = 2_000_000
MAX_PAGES = 500
MAX_CSV_ROWS = 200_000
MAX_DATA_ROWS = 50_000  # structured rows/lines kept for statements
MAX_CELL = 300
TIMEOUT_S = 300  # scanned PDFs are read with OCR, which takes a while
KINDS = {
    ".txt": "text",
    ".md": "text",
    ".csv": "csv",
    ".tsv": "csv",
    ".pdf": "pdf",
    ".mt940": "text",
    ".sta": "text",
    ".xml": "text",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".webp": "image",
    ".xlsx": "sheet",
    ".xlsm": "sheet",
    ".docx": "doc",
    ".html": "html",
    ".htm": "html",
    ".eml": "email",
    ".emlx": "email",
    ".mbox": "mbox",
    ".json": "json",
    ".zip": "zip",
}
SKIP_NAMES = {"passwords.txt", ".passwords"}  # the passwords for protected PDFs live here: never read as a document
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str) -> str:
    return _CTRL.sub("", text)[:MAX_TEXT]


def _read_text(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    data: dict = {"lines": [clean(x)[:600] for x in text.splitlines()[:MAX_DATA_ROWS]]}
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
    return {"kind": "csv", "text": clean(text), "meta": meta, "data": {"rows": [[clean(c)[:MAX_CELL] for c in r][:60] for r in rows[:MAX_DATA_ROWS]]}}


def _read_email(path: Path) -> dict:
    return (readers.read_emlx(path) if path.suffix.lower() == ".emlx" else readers.read_eml(path))[0]


# One reader per kind of file. A new kind of file is a new function here and its extensions in KINDS: nothing else changes. Each returns the same shape
# ({kind, text, meta, data}); a picture comes back with the text OCR found in it, which is how the service later tells a photographed receipt from a holiday photo.
PARSERS: dict[str, Callable[[Path], dict]] = {
    "text": _read_text,
    "csv": _read_csv,
    "pdf": lambda path: readers.read_pdf(path, load_passwords()),
    "image": readers.read_image,
    "sheet": readers.read_sheet,
    "doc": readers.read_docx,
    "html": readers.read_html,
    "email": _read_email,
    "json": readers.read_json,
}


def extract(path: Path) -> dict:
    """In-process extraction with the reader for this kind of file. Called only inside the limited subprocess (or by tests)."""
    reader = PARSERS.get(KINDS.get(path.suffix.lower(), ""))
    if reader is None:
        raise ValueError(f"unsupported file type: {path.suffix}")
    return reader(path)


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
    if len(head) < 2:
        return []
    for delimiter in ("\t", ";", ","):
        counts = {ln.count(delimiter) for ln in head[:5]}
        if len(counts) == 1 and counts != {0} and next(iter(counts)) >= 2:
            reader = csv.reader(text.splitlines(), delimiter=delimiter)
            return [[clean(c)[:MAX_CELL] for c in r][:60] for _, r in zip(range(MAX_DATA_ROWS), reader, strict=False)]
    return []


def _limits() -> None:  # runs in the child before exec (Linux/macOS)
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def extract_isolated(path: Path, timeout: int = TIMEOUT_S) -> dict:
    r = subprocess.run(
        [sys.executable, "-I", "-m", "library.parser", "--extract-one", str(path)], capture_output=True, timeout=timeout, preexec_fn=_limits, check=False
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:] or f"parser exited {r.returncode}")
    return json.loads(r.stdout)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _done(out: Path, digest: str) -> bool:
    """Has this content been read? A marker with no content in it is kept, because the readable copy is deleted once the app has stored it."""
    return (out / ".done" / digest).exists() or (out / f"{digest}.json").exists()


def _write(out: Path, digest: str, label: str, size: int, res: dict, area: str) -> None:
    doc = {
        "schema": SCHEMA,
        "sha256": digest,
        "name": clean(label)[:255],
        "bytes": size,
        "parsed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **({"area": area} if area else {}),
        **res,
    }
    tmp = out / f".{digest}.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    (out / ".done").mkdir(exist_ok=True)
    (out / ".done" / digest).touch()
    os.replace(tmp, out / f"{digest}.json")  # atomic: the app never sees a half-written file


def _process(f: Path, label: str, out: Path, area: str, isolated: bool, counts: dict[str, int], depth: int = 0) -> None:
    """One file. ZIP archives and emails are opened and their files processed one by one (bounded; nothing inside an archive is trusted)."""
    import tempfile

    suffix = f.suffix.lower()
    if f.name.lower() in SKIP_NAMES or suffix not in KINDS or f.stat().st_size > (MBOX_MAX_BYTES if suffix == ".mbox" else MAX_BYTES):
        counts["skipped"] += 1
        return
    digest = sha256(f)
    if area:
        digest = hashlib.sha256((area + digest).encode()).hexdigest()  # the same file in two folders is two documents
    if _done(out, digest):
        return
    try:
        if suffix == ".mbox" and depth == 0:
            _process_mailbox(f, label, out, area, isolated, counts, digest)
            return
        if suffix == ".zip" and depth == 0:
            members = readers.zip_members(f)
            with tempfile.TemporaryDirectory() as tmp:
                for name, content in members:
                    inner = Path(tmp) / name
                    inner.write_bytes(content)
                    _process(inner, f"{label}/{name}", out, area, isolated, counts, depth + 1)
            return
        res = extract_isolated(f) if isolated else extract(f)
        _write(out, digest, label, f.stat().st_size, res, area)
        counts["parsed"] += 1
        if depth and area == "mail" and res["kind"] == "image":
            keep_picture(f)
        if suffix in (".eml", ".emlx") and depth < 2:
            with tempfile.TemporaryDirectory() as tmp:
                for name, content in (readers.read_emlx(f) if suffix == ".emlx" else readers.read_eml(f))[1][:20]:
                    inner = Path(tmp) / Path(name).name
                    inner.write_bytes(content)
                    _process(inner, f"{label}/{name}", out, area, isolated, counts, depth + 1)
    except Exception as e:  # noqa: BLE001 - an unreadable or hostile file must fail only itself, never the whole batch
        print(f"FAILED {label}: {e}", file=sys.stderr, flush=True)
        counts["failed"] += 1


PICTURES_IN = "LIBRARY_PICTURES_IN"  # where a picture that arrived as a mail attachment is kept, for the picture engine to index like any other


def keep_picture(f: Path) -> None:
    """A picture from a mail is also kept as a plain file (named by its content), so the picture engine reads it like every other picture: its date, its
    text, the people in it. Without the folder set, nothing is kept."""
    target_dir = os.environ.get(PICTURES_IN, "")
    if not target_dir:
        return
    folder = Path(target_dir)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{sha256(f)}{f.suffix.lower()}"
    if not target.exists():
        shutil.copyfile(f, target)


def _process_mailbox(f: Path, label: str, out: Path, area: str, isolated: bool, counts: dict[str, int], digest: str) -> None:
    """A mailbox export: every message is parsed as an email (and its attachments as documents). A mailbox already read is not read again."""
    import tempfile

    seen = out / ".seen" / digest
    if seen.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        for n, raw in enumerate(readers.mbox_messages(f), 1):
            inner = Path(tmp) / f"{n:05d}.eml"
            inner.write_bytes(raw)
            _process(inner, f"{label}/{n:05d} {readers.mail_subject(raw)}.eml", out, area, isolated, counts, 1)
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.touch()  # empty: a mail's name can be its subject, and nothing readable is kept here


def process_inbox(inbox: Path, out: Path, isolated: bool = True, area: str = "", skip_folders: frozenset[str] = frozenset()) -> dict[str, int]:
    """Parse every new supported file under inbox into out/<sha256>.json. Same content is never parsed twice. `skip_folders` are top-level folders handled elsewhere."""
    out.mkdir(parents=True, exist_ok=True)
    root = inbox.resolve()
    counts = {"parsed": 0, "skipped": 0, "failed": 0}
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.is_symlink() or root not in f.resolve().parents:
            continue
        if f.relative_to(root).parts[0] in skip_folders:
            continue
        _process(f, f.name, out, area, isolated, counts)
    return counts


MAIL_SKIP_MAILBOXES = frozenset({"junk", "junk e-mail", "spam", "trash", "deleted messages", "deleted items", "drafts"})
MAIL_SAVE_EVERY = 200  # the list of messages already read is saved this often, so an interrupted first read carries on where it stopped


def _in_skipped_mailbox(relative: Path) -> bool:
    return any(part.lower().removesuffix(".mbox") in MAIL_SKIP_MAILBOXES for part in relative.parts[:-1] if part.lower().endswith(".mbox"))


def _save_seen(cache_file: Path, seen: dict[str, str]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(seen))


def process_mail_store(store: Path, out: Path, isolated: bool = True) -> dict[str, int]:
    """Apple Mail's own folder (read-only): every message file except Junk, Trash and Drafts, only those not read before (a message is recognised by its
    path, size and time, so the folder is not re-read every round). Messages become documents with the area `mail`, attachments included."""
    out.mkdir(parents=True, exist_ok=True)
    root = store.resolve()
    cache_file = out / ".mailseen" / (hashlib.sha256(str(root).encode()).hexdigest()[:16] + ".json")
    try:
        seen: dict[str, str] = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    except (OSError, ValueError):
        seen = {}
    counts = {"parsed": 0, "skipped": 0, "failed": 0}
    for f in sorted(root.rglob("*.emlx")):
        if f.is_symlink() or root not in f.resolve().parents:
            continue
        relative = f.relative_to(root)
        if _in_skipped_mailbox(relative):
            continue
        stat = f.stat()
        stamp = f"{stat.st_size}:{int(stat.st_mtime)}"
        if seen.get(str(relative)) == stamp:
            continue
        _process(f, f.name, out, "mail", isolated, counts)
        seen[str(relative)] = stamp
        if counts["parsed"] % MAIL_SAVE_EVERY == 0:
            _save_seen(cache_file, seen)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(seen))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="library-parser")
    ap.add_argument("--inbox", default=os.environ.get("ATLAS_INBOX", str(Path.home() / "AtlasInbox")))
    ap.add_argument("--out", default=os.environ.get("ATLAS_PARSED", str(Path.home() / "AtlasParsed")))
    ap.add_argument(
        "--collection",
        action="append",
        default=[c for c in os.environ.get("LIBRARY_COLLECTIONS", "").split(",") if c],
        help="NAME=PATH: a folder you keep for one purpose (finance=/finance, health=/health), read-only; its files are always read and carry that name",
    )
    ap.add_argument("--mail", default=os.environ.get("ATLAS_MAIL", ""), help="Apple Mail's own folder (read-only): all mail except Junk, Trash and Drafts")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--extract-one", metavar="FILE", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.extract_one:
        sys.stdout.write(json.dumps(extract(Path(a.extract_one)), ensure_ascii=False))
        return 0
    out = Path(a.out)
    while True:
        out.mkdir(parents=True, exist_ok=True)
        (out / BUSY).touch()  # tells the Documents service that more may still be coming
        try:
            res = read_everything(a)
        finally:
            (out / BUSY).unlink(missing_ok=True)
        if res["parsed"] or res["failed"]:
            print(res, flush=True)
        if not a.watch:
            return 0
        _wait_for_next_round(out)


BUSY = ".busy"  # exists while a round is running
WAKE = ".wake"  # the Documents service touches it when you press Update: start a round now
ROUND_SECONDS = 30


COLLECTION_NAME = re.compile(r"^[a-z]{2,20}$")


def collections(specs: list[str]) -> list[tuple[str, Path]]:
    """`name=path` pairs. A name is lower-case letters only and cannot be `mail` (that one is for mail); anything else is ignored."""
    found = []
    for spec in specs:
        name, _, folder = spec.partition("=")
        if COLLECTION_NAME.match(name) and name != "mail" and folder:
            found.append((name, Path(folder)))
    return found


def _supported(root: Path, skip: frozenset[str] = frozenset(), only_emlx: bool = False) -> int:
    """How many files under root the reader would take (by name only: fast), so the person is shown the full number, not a guess."""
    total = 0
    for f in root.resolve().rglob("*"):
        if f.name.startswith(".") or f.is_symlink() or not f.is_file() or f.name.lower() in SKIP_NAMES:
            continue
        relative = f.relative_to(root.resolve())
        if relative.parts[0] in skip or (only_emlx and (f.suffix.lower() != ".emlx" or _in_skipped_mailbox(relative))):
            continue
        total += f.suffix.lower() in KINDS
    return total


FOUND_FILE = ".found"


def write_found(a: argparse.Namespace) -> None:
    """Count what is there before reading it: files in the inbox and collections, and mail. The app shows these as the totals."""
    documents = _supported(Path(a.inbox), skip=frozenset({"mail"}))
    for _name, folder in collections(a.collection):
        if folder.is_dir():
            documents += _supported(folder)
    mails = _supported(Path(a.inbox) / "mail") if (Path(a.inbox) / "mail").is_dir() else 0
    if a.mail and Path(a.mail).is_dir():
        mails += _supported(Path(a.mail), only_emlx=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f"{FOUND_FILE}.tmp"
    tmp.write_text(json.dumps({"documents": documents, "mails": mails}))
    os.replace(tmp, out / FOUND_FILE)


def read_everything(a: argparse.Namespace) -> dict[str, int]:
    """One round: the inbox, every collection folder, mail exports in the inbox, and Apple Mail's own folder."""
    write_found(a)
    res = process_inbox(Path(a.inbox), Path(a.out), skip_folders=frozenset({"mail"}))
    extra = []
    for name, folder in collections(a.collection):
        if folder.is_dir():
            extra.append(process_inbox(folder, Path(a.out), area=name))
    if (Path(a.inbox) / "mail").is_dir():  # mail exports dropped into the inbox (.mbox, .eml, .emlx)
        extra.append(process_inbox(Path(a.inbox) / "mail", Path(a.out), area="mail"))
    if a.mail and Path(a.mail).is_dir():
        extra.append(process_mail_store(Path(a.mail), Path(a.out)))
    for more in extra:
        res = {k: res[k] + more[k] for k in res}
    return res


def _wait_for_next_round(out: Path) -> None:
    for _ in range(ROUND_SECONDS):
        if (out / WAKE).exists():
            (out / WAKE).unlink(missing_ok=True)
            return
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
