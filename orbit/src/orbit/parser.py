"""The isolated parser: turns untrusted files (PDF incl. scans, images, spreadsheets, Word, web pages, emails, JSON, ZIP, CSV, text) into one plain JSON shape. It is the only code that opens them.

Runs in its own container with NO network, the inbox mounted read-only, and a single writable output folder that the
app mounts read-only. Each file is parsed in a throw-away subprocess with CPU, memory and time limits, so a hostile or
broken file can at worst fail that one file. Output is JSON only (never pickle), text capped and stripped of control
characters; the app still treats it as untrusted data.

    orbit-parser --once  [--inbox /inbox --out /parsed]
    orbit-parser --watch
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
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


def extract(path: Path) -> dict:
    """In-process extraction. Called only inside the limited subprocess (or by tests)."""
    kind = KINDS.get(path.suffix.lower())
    meta: dict = {}
    data: dict = {}
    if kind == "text":
        text = path.read_text(encoding="utf-8", errors="replace")
    elif kind == "csv":
        head = path.read_bytes()[:4096].decode("utf-8", "replace")
        delimiter = max((",", ";", "\t"), key=head.split("\n")[0].count)  # Dutch banks export with ; or tab
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
            rows = []
            for i, row in enumerate(csv.reader(f, delimiter=delimiter)):
                if i >= MAX_CSV_ROWS:
                    meta["truncated"] = True
                    break
                rows.append(row)
        meta["rows"] = len(rows)
        meta["columns"] = [clean(c)[:80] for c in rows[0]][:50] if rows else []
        text = "\n".join(" | ".join(r) for r in rows)
        data["rows"] = [[clean(c)[:MAX_CELL] for c in r][:60] for r in rows[:MAX_DATA_ROWS]]  # exact cells, for statements
    elif kind == "pdf":
        return readers.read_pdf(path, load_passwords())
    elif kind == "image":
        return readers.read_image(path)
    elif kind == "sheet":
        return readers.read_sheet(path)
    elif kind == "doc":
        return readers.read_docx(path)
    elif kind == "html":
        return readers.read_html(path)
    elif kind == "email":
        return (readers.read_emlx(path) if path.suffix.lower() == ".emlx" else readers.read_eml(path))[0]
    elif kind == "json":
        return readers.read_json(path)
    else:
        raise ValueError(f"unsupported file type: {path.suffix}")
    if kind == "text":
        data["lines"] = [clean(x)[:600] for x in text.splitlines()[:MAX_DATA_ROWS]]
        rows = _delimited_rows(text)  # a plain tab- or semicolon-separated export (some banks give these with no header row)
        if rows:
            data["rows"] = rows
    return {"kind": kind, "text": clean(text), "meta": meta, "data": data}


_table_lines = readers.table_lines
_visual_lines = readers.visual_lines


def load_passwords() -> list[str]:
    """Passwords for protected PDFs: one per line in passwords.txt (in your finance folder, or the file named by ORBIT_PASSWORDS_FILE). Never stored."""
    candidates = [os.environ.get("ORBIT_PASSWORDS_FILE", "")] + [
        str(Path(os.environ.get(k, "")) / "passwords.txt") for k in ("ORBIT_FINANCE", "ORBIT_INBOX") if os.environ.get(k)
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
        [sys.executable, "-I", "-m", "orbit.parser", "--extract-one", str(path)], capture_output=True, timeout=timeout, preexec_fn=_limits, check=False
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
    if (out / f"{digest}.json").exists():
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
        if suffix in (".eml", ".emlx") and depth < 2:
            with tempfile.TemporaryDirectory() as tmp:
                for name, content in (readers.read_emlx(f) if suffix == ".emlx" else readers.read_eml(f))[1][:20]:
                    inner = Path(tmp) / Path(name).name
                    inner.write_bytes(content)
                    _process(inner, f"{label}/{name}", out, area, isolated, counts, depth + 1)
    except Exception as e:  # noqa: BLE001 - an unreadable or hostile file must fail only itself, never the whole batch
        print(f"FAILED {label}: {e}", file=sys.stderr, flush=True)
        counts["failed"] += 1


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
    seen.write_text(label)


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
MAIL_BATCH = 1500  # new messages read per round, so a large mail store never blocks the other folders


def _in_skipped_mailbox(relative: Path) -> bool:
    return any(part.lower().removesuffix(".mbox") in MAIL_SKIP_MAILBOXES for part in relative.parts[:-1] if part.lower().endswith(".mbox"))


def process_mail_store(store: Path, out: Path, isolated: bool = True, batch: int = MAIL_BATCH) -> dict[str, int]:
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
    done = 0
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
        if done >= batch:
            break
        _process(f, f.name, out, "mail", isolated, counts)
        seen[str(relative)] = stamp
        done += 1
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(seen))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="orbit-parser")
    ap.add_argument("--inbox", default=os.environ.get("ORBIT_INBOX", str(Path.home() / "OrbitInbox")))
    ap.add_argument("--out", default=os.environ.get("ORBIT_PARSED", str(Path.home() / "OrbitParsed")))
    ap.add_argument("--finance", default=os.environ.get("ORBIT_FINANCE", ""), help="folder of bank statements and finance files (read-only)")
    ap.add_argument("--mail", default=os.environ.get("ORBIT_MAIL", ""), help="Apple Mail's own folder (read-only): all mail except Junk, Trash and Drafts")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--extract-one", metavar="FILE", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.extract_one:
        sys.stdout.write(json.dumps(extract(Path(a.extract_one)), ensure_ascii=False))
        return 0
    while True:
        res = process_inbox(Path(a.inbox), Path(a.out), skip_folders=frozenset({"mail"}))
        extra = []
        if a.finance and Path(a.finance).is_dir():
            extra.append(process_inbox(Path(a.finance), Path(a.out), area="finance"))
        if (Path(a.inbox) / "mail").is_dir():  # mail exports dropped into the inbox (.mbox, .eml, .emlx)
            extra.append(process_inbox(Path(a.inbox) / "mail", Path(a.out), area="mail"))
        if a.mail and Path(a.mail).is_dir():
            extra.append(process_mail_store(Path(a.mail), Path(a.out)))
        for more in extra:
            res = {k: res[k] + more[k] for k in res}
        if res["parsed"] or res["failed"]:
            print(res, flush=True)
        if not a.watch:
            return 0
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
