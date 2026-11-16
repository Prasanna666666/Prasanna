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
import contextlib
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import flags, priority, readers, sniff

SCHEMA = 1
MAX_BYTES = 50 * 1024 * 1024
MBOX_MAX_BYTES = 64 * 1024 * 1024 * 1024  # a whole mailbox export can be large; each message inside is still capped
MAX_TEXT = 2_000_000
MAX_PAGES = 500
MAX_CSV_ROWS = 200_000
MAX_DATA_ROWS = 50_000  # structured rows/lines kept for statements
MAX_CELL = 300
TIMEOUT_S = 300  # scanned PDFs are read with OCR, which takes a while
SKIP_NAMES = {"passwords.txt", ".passwords"}  # the passwords for protected PDFs live here: never read as a document
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str) -> str:
    return _CTRL.sub("", text)[:MAX_TEXT]


def _read_text(path: Path) -> dict:
    text = sniff.decode_text(path.read_bytes()[: 20 * 1024 * 1024]) or path.read_text(encoding="utf-8", errors="replace")
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
    """In-process extraction with the reader for this kind of file. Called only inside the limited subprocess (or by tests)."""
    return PARSERS[sniff.kind_of(path)](path)


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


def _done(out: Path, digest: str) -> bool:
    """Has this content been read? A marker with no content in it is kept, because the readable copy is deleted once the app has stored it."""
    return (out / ".done" / digest).exists() or (out / f"{digest}.json").exists()


def _write(out: Path, digest: str, label: str, size: int, res: dict, area: str, source: str = "") -> None:
    doc = {
        "schema": SCHEMA,
        "sha256": digest,
        "name": clean(label)[:255],
        "bytes": size,
        "parsed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **({"area": area} if area else {}),
        **({"source": source[:600]} if source else {}),  # where the file lies, so a newer version of the same file replaces the older one
        **res,
    }
    tmp = out / f".{digest}.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    (out / ".done").mkdir(exist_ok=True)
    (out / ".done" / digest).touch()
    os.replace(tmp, out / f"{digest}.json")  # atomic: the app never sees a half-written file


_CLAIMED: set[str] = set()
_FAILED: list[str] = []  # files that could not be read in this round, with the reason
MAX_FAILED = 200
_CLAIM_LOCK = threading.Lock()


def _identity(f: Path, kind: str, area: str) -> str:
    """What makes a file the same file: its content, and the folder kind it lies in (the same file in two folders is two documents)."""
    digest = sha256(f)
    if kind == "pdf" and not sniff.head_of(f).startswith(b"%PDF"):
        digest = hashlib.sha256((digest + "pdf-after-stray-bytes").encode()).hexdigest()  # read wrongly before: read again, the older version is replaced
    return hashlib.sha256((area + digest).encode()).hexdigest() if area else digest


ATTACHED = ".attached-2"  # marks the mails whose attachments have all been taken out (by the method of this version)
MAIL_DEPTH = 3  # a mail forwarded inside a mail still gets its attachments read


def _now(out: Path, name: str, step: str = "") -> None:
    """What the reader is on, for the Documents service to show: the name, and (when it is not simply reading a file) what it is doing."""
    with contextlib.suppress(OSError):
        (out / ".now").write_text(f"{name[:200]}\n{step[:100]}")


def _process_attachments(f: Path, label: str, out: Path, area: str, isolated: bool, counts: dict[str, int], depth: int, digest: str) -> None:
    """Every document a mail carries is read as a document of its own; the mail is then marked, so it is not opened again for this."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        for name, content in (readers.read_emlx(f) if _is_emlx(f) else readers.read_eml(f))[1]:
            inner = Path(tmp) / f"{abs(hash(name)) % 10**8}-{Path(name).name}"  # two attachments with one name stay two files
            inner.write_bytes(content)
            _process(inner, f"{label}/{name}", out, area, isolated, counts, depth + 1)
    (out / ATTACHED).mkdir(parents=True, exist_ok=True)
    (out / ATTACHED / digest).touch()


def _plain_reason(error: Exception) -> str:
    """Why a file could not be read, in plain words (never the program's own message, which is code)."""
    message = str(error).lower()
    if "password" in message or "encrypted" in message:
        return "locked with a password (put the password in passwords.txt in your finance folder)"
    if "memory" in message or isinstance(error, MemoryError):
        return "too big to open here"
    return "damaged, or not a real file of its kind"


def _too_large(size: int, kind: str, label: str, counts: dict[str, int]) -> bool:
    if size <= (MBOX_MAX_BYTES if kind == "mbox" else MAX_BYTES):
        return False
    counts["skipped"] += 1
    with _CLAIM_LOCK:
        if len(_FAILED) < MAX_FAILED:
            _FAILED.append(f"{label[:120]}: too large to read")
    return True


def _process(f: Path, label: str, out: Path, area: str, isolated: bool, counts: dict[str, int], depth: int = 0, source: str = "") -> None:
    """One file. ZIP archives and emails are opened and their files processed one by one (bounded; nothing inside an archive is trusted)."""
    import tempfile

    size = f.stat().st_size
    if f.name.lower() in SKIP_NAMES or size == 0 or size > MBOX_MAX_BYTES:
        counts["skipped"] += 1
        return
    try:
        kind = sniff.kind_of(f)
    except (OSError, ValueError):
        kind = "binary"
    if _is_bulk_message(f, kind, area, depth) or _too_large(size, kind, label, counts):
        return  # a newsletter, promotion or mailing list (not counted among the mails to read), or a file too large to read (said as unread)
    digest = _identity(f, kind, area)
    if _done(out, digest):
        if kind == "email" and depth < MAIL_DEPTH and not (out / ATTACHED / digest).exists():
            _process_attachments(
                f, label, out, area, isolated, counts, depth, digest
            )  # a mail read before its attachments were all taken out: once more, for those
        return
    with _CLAIM_LOCK:  # files read at the same moment with the same content: only the first one reads it
        if digest in _CLAIMED:
            return
        _CLAIMED.add(digest)
    try:
        if kind == "mbox" and depth == 0:
            _process_mailbox(f, label, out, area, isolated, counts, digest)
            return
        if kind == "zip" and depth < 2:  # a package (an archive, an e-book, an Apple Pages or Keynote file): its members are read one by one
            members = readers.zip_members(f)
            with tempfile.TemporaryDirectory() as tmp:
                for name, content in members:
                    inner = Path(tmp) / name
                    inner.write_bytes(content)
                    _process(inner, f"{label}/{name}", out, area, isolated, counts, depth + 1)
            return
        _now(out, label)
        res = (
            extract_isolated(f) if isolated and kind != "email" else extract(f)
        )  # a mail is plain text parsed by the standard library, inside this sealed container: a sealed child per message would take a thousand times longer
        _write(out, digest, label, f.stat().st_size, res, area, source if depth == 0 else "")
        counts["parsed"] += 1
        if _BUDGET["left"] is not None:
            _BUDGET["left"] -= 1
        if depth and area == "mail" and res["kind"] == "image":
            keep_picture(f)
        if kind == "email" and depth < MAIL_DEPTH:
            _process_attachments(f, label, out, area, isolated, counts, depth, digest)
    except Exception as e:  # noqa: BLE001 - an unreadable or hostile file must fail only itself, never the whole batch
        print(f"FAILED {label}: {e}", file=sys.stderr, flush=True)
        counts["failed"] += 1
        with _CLAIM_LOCK:
            if len(_FAILED) < MAX_FAILED:
                _FAILED.append(f"{label[:120]}: {_plain_reason(e)}")


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

    seen = out / ".seen-2" / digest
    if seen.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        for n, raw in enumerate(readers.mbox_messages(f), 1):
            inner = Path(tmp) / f"{n:05d}.eml"
            inner.write_bytes(raw)
            _process(inner, f"{label}/{n:05d} {readers.mail_subject(raw)}.eml", out, area, isolated, counts, 1)
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.touch()  # empty: a mail's name can be its subject, and nothing readable is kept here


WORKERS = max(
    1, min(int(os.environ.get("LIBRARY_PARSE_WORKERS", str(max(2, min(os.cpu_count() or 2, 4))))), 12)
)  # files read at the same time (up to four: the rest of the Mac stays free), each in its own sealed child process
BATCH = 50  # files per batch: a pause or stop takes effect within one batch


_BUDGET: dict[str, int | None] = {"left": None}  # files this round may still read; None: no limit (the person pressed the button)


def _start_budget(out: Path) -> None:
    """A round the person starts reads everything. A round that started by itself reads at most the number the service wrote, then stops and says so."""
    _BUDGET["left"] = None
    (out / flags.AUTO_CAPPED).unlink(missing_ok=True)
    limit = out / flags.AUTO_LIMIT
    with contextlib.suppress(OSError, ValueError):
        _BUDGET["left"] = max(1, int(limit.read_text().strip()))
    limit.unlink(missing_ok=True)


def checkpoint(out: Path) -> bool:
    """Between batches: wait while paused, rest a moment, and say whether the round should end now (stopped, or an automatic round has used up its limit)."""
    while (out / PAUSE).exists() and not (out / STOP).exists():
        time.sleep(1)
    time.sleep(GENTLE_SECONDS)
    left = _BUDGET["left"]
    if left is not None and left <= 0:
        (out / flags.AUTO_CAPPED).touch()
        return True
    return (out / STOP).exists()


_UNREAD = {"documents": 0, "mails": 0, "attachments": 0}  # files and mails this round that could not be read (failed, or too large)
_PROGRESS = {
    "documents": 0,
    "mails": 0,
    "attachments": 0,
}  # files gone through in this round, by what they are (every file counts once it has been looked at: read, already known, left out or unreadable)


def _progress_add(out: Path, area: str, n: int, group: str = "", unread: int = 0) -> None:
    key = group or ("mails" if area == "mail" else "documents")
    _PROGRESS[key] += n
    _UNREAD[key] += unread
    _write_progress(out)


def _write_progress(out: Path) -> None:
    with contextlib.suppress(OSError):
        tmp = out / ".progress.tmp"
        tmp.write_text(json.dumps({**_PROGRESS, "unread": _UNREAD}))
        os.replace(tmp, out / ".progress")
        failed = out / ".unread-files.tmp"
        failed.write_text(json.dumps(_FAILED[:MAX_FAILED]))  # what could not be read so far, for the card
        os.replace(failed, out / ".unread-files")


def _read_batch(files: list[Path], label_of, out: Path, area: str, isolated: bool, source_of=None, group: str = "") -> dict[str, int]:
    """Read these files at the same time (each in its own child process); the totals of what happened."""
    total = {"parsed": 0, "skipped": 0, "failed": 0}
    with _CLAIM_LOCK:
        _CLAIMED.clear()  # claims only matter within one batch; a file that failed is tried again next round

    def one(f: Path) -> dict[str, int]:
        counts = {"parsed": 0, "skipped": 0, "failed": 0}
        _process(f, label_of(f), out, area, isolated, counts, 0, source_of(f) if source_of else "")
        return counts

    unread = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for counts in pool.map(one, files):
            for k, v in counts.items():
                total[k] += v
            unread += bool(
                counts["failed"] or counts["skipped"]
            )  # a file counts as read only when it was read fully, without anything failing or being left out
    _progress_add(out, area, len(files) - unread, group, unread)
    return total


def process_inbox(inbox: Path, out: Path, isolated: bool = True, area: str = "", skip_folders: frozenset[str] = frozenset()) -> dict[str, int]:
    """Parse every new supported file under inbox into out/<sha256>.json. Same content is never parsed twice. `skip_folders` are top-level folders handled elsewhere."""
    out.mkdir(parents=True, exist_ok=True)
    root = inbox.resolve()
    counts = {"parsed": 0, "skipped": 0, "failed": 0}
    files = [
        f
        for f in sorted(root.rglob("*"))
        if f.is_file()
        and not f.is_symlink()
        and not f.name.startswith(".")
        and f.name.lower() not in SKIP_NAMES
        and root in f.resolve().parents
        and f.relative_to(root).parts[0] not in skip_folders
        and f.stat().st_size > 0
    ]
    for i in range(0, len(files), BATCH):
        for k, v in _read_batch(files[i : i + BATCH], lambda f: f.name, out, area, isolated, lambda f: f"{root}|{f.relative_to(root)}").items():
            counts[k] += v
        if checkpoint(out):
            break
    return counts


def mailboxes_read() -> frozenset[str]:
    """The names of the mailboxes that are read (`mailboxes.json`, or LIBRARY_MAILBOXES): everything else in the mail folder is skipped."""
    env = os.environ.get("LIBRARY_MAILBOXES")
    if env is not None:
        return frozenset(n.strip().lower() for n in env.split(",") if n.strip())
    try:
        raw = json.loads(Path(__file__).with_name("mailboxes.json").read_text()).get("read", [])
    except (OSError, ValueError, AttributeError):
        raw = []
    return frozenset(str(n).strip().lower() for n in raw)


def _bulk_headers() -> dict[str, str]:
    """The headers that mark bulk mail (newsletters, promotions, mailing lists), as declared in `mailboxes.json`: header name to the words that count ('' = any value)."""
    try:
        raw = json.loads(Path(__file__).with_name("mailboxes.json").read_text()).get("bulk", {})
    except (OSError, ValueError, AttributeError):
        raw = {}
    return {str(k).lower(): str(v).lower() for k, v in raw.items()} if isinstance(raw, dict) else {}


def is_bulk_mail(path: Path) -> bool:
    """Does this message carry a header that marks it as bulk mail? Only its headers are read."""
    import email.parser

    wanted = _bulk_headers()
    if not wanted:
        return False
    try:
        with path.open("rb") as f:
            raw = f.read(16384)
    except OSError:
        return False
    if path.suffix.lower() == ".emlx" or sniff.is_emlx(raw[:64]):
        raw = raw.partition(b"\n")[2]  # the first line of an Apple Mail file is the length of the message
    head = email.parser.BytesParser().parsebytes(raw, headersonly=True)
    for name, words in wanted.items():
        value = str(head.get(name, "")).lower()
        if value and (not words or any(w in value for w in words.split())):
            return True
    return False


def _is_bulk_message(f: Path, kind: str, area: str, depth: int) -> bool:
    return kind == "email" and area == "mail" and depth < 2 and str(f) not in _VETTED and is_bulk_mail(f)


def _in_skipped_mailbox(relative: Path) -> bool:
    """A message is read only when the mailbox it lies in (the innermost folder) is one of those declared: a folder you made, promotions, archives and the rest are not."""
    boxes = [part for part in relative.parts[:-1] if part.lower().endswith(".mbox")]
    return not boxes or boxes[-1].lower().removesuffix(".mbox") not in mailboxes_read()


def _save_seen(cache_file: Path, seen: dict[str, str]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(seen))


_MAIL_INDEX: dict[str, MailIndex] = {}
_INDEX_LOCK = threading.Lock()
_VETTED: set[str] = set()  # messages already checked for being bulk mail: not opened again


class MailIndex:
    """One walk through Apple Mail's folder, made once per round and shared by the counting and the reading: the messages of the mailboxes that are read (not bulk mail), how many of
    them were read before, the bulk messages found now, and the attachments Mail keeps as files of their own beside the messages."""

    def __init__(self) -> None:
        self.messages: list[tuple[Path, str, str]] = []  # (file, path inside the Mail folder, size:time) still to read
        self.gone = 0  # messages read in an earlier round
        self.new_bulk: dict[str, str] = {}  # newsletters, promotions and mailing lists seen now: remembered, never counted
        self.attachments: list[tuple[Path, str]] = []

    @property
    def mails(self) -> int:
        return len(self.messages) + self.gone


def _seen_cache(out: Path, root: Path, kind: str = "") -> tuple[Path, dict[str, str]]:
    cache_file = out / ".mailseen-2" / (hashlib.sha256((kind + str(root)).encode()).hexdigest()[:16] + ".json")
    try:
        return cache_file, json.loads(cache_file.read_text()) if cache_file.exists() else {}
    except (OSError, ValueError):
        return cache_file, {}


def _build_mail_index(root: Path, out: Path) -> MailIndex:
    idx = MailIndex()
    _, seen = _seen_cache(out, root)
    bulk_owners: set[tuple[str, str]] = set()
    candidates: list[tuple[Path, str, tuple[str, str]]] = []
    for n, f in enumerate(root.rglob("*"), 1):  # one look at every file, not sorted first, so Pause and Stop are heard during the walk
        if n % CHECK_EVERY == 0:
            _now(out, "Mail", f"looking for new messages ({n:,} looked at)")
            if halted(out):
                raise Halted
        if f.name.startswith(".") or f.is_symlink():
            continue
        inside = f.relative_to(root)
        if _in_skipped_mailbox(inside):
            continue
        if f.suffix.lower() == ".emlx":
            stat = f.stat()
            stamp, key = f"{stat.st_size}:{int(stat.st_mtime)}", str(inside)
            owner = (str(f.parent), f.name.split(".")[0])
            if seen.get(key) == f"bulk:{stamp}":
                bulk_owners.add(owner)
            elif seen.get(key) == stamp:
                idx.gone += 1
            elif is_bulk_mail(f):
                idx.new_bulk[key] = stamp
                bulk_owners.add(owner)
            else:
                idx.messages.append((f, key, stamp))
                _VETTED.add(str(f))
        elif "Attachments" in inside.parts and f.is_file():
            at = inside.parts.index("Attachments")
            if len(inside.parts) > at + 2:
                candidates.append((f, str(inside), (str(root.joinpath(*inside.parts[:at], "Messages")), inside.parts[at + 1])))
    idx.attachments = [
        (f, rel) for f, rel, owner in candidates if owner not in bulk_owners and f.stat().st_size > 0
    ]  # an attachment of a newsletter or promotion is not read
    return idx


def mail_index(store: Path, out: Path) -> MailIndex:
    """The walk through the Mail folder, made once in a round: whoever asks first does it, the other gets the same result."""
    key = str(store.resolve())
    with _INDEX_LOCK:
        if key not in _MAIL_INDEX:
            _MAIL_INDEX[key] = _build_mail_index(Path(key), out)
        return _MAIL_INDEX[key]


def process_mail_attachments(store: Path, out: Path, isolated: bool = True) -> dict[str, int]:
    """The attachments Apple Mail keeps beside the messages are read as documents of the mail (the ones not read before)."""
    out.mkdir(parents=True, exist_ok=True)
    root = store.resolve()
    counts = {"parsed": 0, "skipped": 0, "failed": 0}
    try:
        idx = mail_index(root, out)
    except Halted:
        return counts
    cache_file, seen = _seen_cache(out, root, "attachments")
    todo = []
    gone = 0
    for f, relative in idx.attachments:
        stat = f.stat()
        stamp = f"{stat.st_size}:{int(stat.st_mtime)}"
        if seen.get(relative) == stamp:
            gone += 1
        else:
            todo.append((f, relative, stamp))
    _progress_add(out, "mail", gone, "attachments")
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        for k, v in _read_batch([f for f, _, _ in batch], lambda f: "/".join(f.parts[-3:]), out, "mail", isolated, group="attachments").items():
            counts[k] += v
        for _f, relative, stamp in batch:
            seen[relative] = stamp
        _save_seen(cache_file, seen)
        if checkpoint(out):
            break
    return counts


def process_mail_store(store: Path, out: Path, isolated: bool = True) -> dict[str, int]:
    """Apple Mail's own folder (read-only): the messages of the declared mailboxes (`mailboxes.json`), not bulk mail, only those not read before (a message is recognised by its
    path, size and time, so the folder is not re-read every round). Messages become documents with the area `mail`."""
    out.mkdir(parents=True, exist_ok=True)
    root = store.resolve()
    counts = {"parsed": 0, "skipped": 0, "failed": 0}
    try:
        idx = mail_index(root, out)
    except Halted:
        return counts  # stopped while looking through the mail folder
    cache_file, seen = _seen_cache(out, root)
    seen.update({k: f"bulk:{v}" for k, v in idx.new_bulk.items()})  # remembered, so their headers are not read again
    _progress_add(out, "mail", idx.gone)
    for i in range(
        0, len(idx.messages), BATCH
    ):  # a batch at a time, several messages at once; what is done is remembered after each batch, so an interrupted first read carries on
        batch = idx.messages[i : i + BATCH]
        for k, v in _read_batch([f for f, _, _ in batch], lambda f: f.name, out, "mail", isolated).items():
            counts[k] += v
        for _f, relative, stamp in batch:
            seen[relative] = stamp
        _save_seen(cache_file, seen)
        if checkpoint(out):
            break
    _save_seen(cache_file, seen)
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
    ap.add_argument(
        "--mail",
        default=os.environ.get("ATLAS_MAIL", ""),
        help="Apple Mail's own folder (read-only): only the mailboxes declared in mailboxes.json (Inbox and Sent)",
    )
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--extract-one", metavar="FILE", help=argparse.SUPPRESS)
    ap.add_argument(
        "--check",
        nargs="?",
        const=0,
        type=int,
        metavar="N",
        help="read every file (or an even sample of N) without storing anything and print what came out, by kind of file",
    )
    a = ap.parse_args(argv)
    if a.check is not None:
        from . import selfcheck

        roots = [("inbox", Path(a.inbox)), *collections(a.collection)]
        print(selfcheck.render(selfcheck.check(roots, a.check)))
        return 0
    if a.extract_one:
        _limits()  # the child limits itself before it opens the file (a limit set by the parent needs preexec_fn, which is unsafe with threads)
        sys.stdout.write(json.dumps(extract(Path(a.extract_one)), ensure_ascii=False))
        return 0
    out = Path(a.out)
    with contextlib.suppress(OSError):
        os.nice(10)  # reading is never more important than what the person is doing; the children inherit this
    while True:
        out.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            (out / ".ocr-engine").write_text(
                "apple" if readers.apple_ocr_running() else "tesseract"
            )  # which text recognition the pages are read with: the Documents service re-reads old scans once it is Apple's
        if a.watch:
            _wait_for_next_round(out)  # nothing is read until the person asks (so starting the computer never starts a big read)
        (out / STOP).unlink(missing_ok=True)
        (out / BUSY).touch()  # tells the Documents service that more may still be coming
        try:
            res = read_everything(a)
        finally:
            (out / BUSY).unlink(missing_ok=True)
            (out / ".now").unlink(missing_ok=True)
        (out / FAILED_FILE).write_text(json.dumps(_FAILED[:MAX_FAILED]))  # what could not be read this round, for the report
        _FAILED.clear()
        if res["parsed"] or res["failed"]:
            print(res, flush=True)
        if not a.watch:
            return 0


PAUSE = ".pause"  # while it exists the reader waits where it is; remove it and it carries on
STOP = ".stop"  # while it exists the round in progress ends at the next safe point
GENTLE_SECONDS = float(
    os.environ.get("LIBRARY_GENTLE_SECONDS", "0")
)  # a short rest after every batch, so the computer stays responsive while a big mailbox is read
BUSY = ".busy"  # exists while a round is running
WAKE = ".wake"  # the Documents service touches it when you press Read new files: start a round now
ROUND_SECONDS = int(os.environ.get("ATLAS_AUTO_ROUND_SECONDS", "0"))  # 0: reading starts only when asked


COLLECTION_NAME = re.compile(r"^[a-z]{2,20}$")


def collections(specs: list[str]) -> list[tuple[str, Path]]:
    """`name=path` pairs. A name is lower-case letters only and cannot be `mail` (that one is for mail); anything else is ignored."""
    found = []
    for spec in specs:
        name, _, folder = spec.partition("=")
        if COLLECTION_NAME.match(name) and name != "mail" and folder:
            found.append((name, Path(folder)))
    return found


class Halted(Exception):
    """The person pressed Stop while the reader was still looking through the folders."""


CHECK_EVERY = 200  # files looked at between two looks at Pause and Stop


def halted(out: Path) -> bool:
    """Wait while paused; true when stopped. Called often during the walks through the folders, so Pause and Stop work there too, not only between batches."""
    while (out / PAUSE).exists() and not (out / STOP).exists():
        time.sleep(1)
    return (out / STOP).exists()


def _supported(root: Path, skip: frozenset[str] = frozenset(), only_emlx: bool = False, out: Path | None = None) -> int:
    """How many files under root the reader will take: every ordinary file with something in it that is not larger than it reads, whatever its type, so the person is shown
    the full number, not a guess."""
    total = 0
    for seen, f in enumerate(root.resolve().rglob("*"), 1):
        if out is not None and seen % CHECK_EVERY == 0 and halted(out):
            raise Halted
        if f.name.startswith(".") or f.is_symlink() or not f.is_file() or f.name.lower() in SKIP_NAMES:
            continue
        relative = f.relative_to(root.resolve())
        if relative.parts[0] in skip or (only_emlx and (f.suffix.lower() != ".emlx" or _in_skipped_mailbox(relative) or is_bulk_mail(f))):
            continue
        size = f.stat().st_size
        total += size > 0  # a file too large to read is counted too: it will be said to be unread, not left out of the count
    return total


FOUND_FILE = ".found"
FAILED_FILE = ".failed.json"


UNREAD_EXAMPLES = 30


def unread_report(roots: list[tuple[str, Path]], out: Path) -> dict[str, Any]:
    """Every file in the folders that will NOT be read, and why: in iCloud but not downloaded, a shortcut or alias, or too large. Every other type of file is read, by what
    is inside it. Hidden system files are not mentioned. Examples are named so the person can look for them."""
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}

    def note(reason: str, label: str, rel: Path) -> None:
        counts[reason] = counts.get(reason, 0) + 1
        if len(examples.setdefault(reason, [])) < UNREAD_EXAMPLES:
            examples[reason].append(f"{label}: {rel}")

    for label, root in roots:
        top = root.resolve()
        for seen, f in enumerate(top.rglob("*"), 1):
            if seen % CHECK_EVERY == 0 and halted(out):
                raise Halted
            name = f.name
            rel = f.relative_to(top)
            if name.startswith("."):
                if name.endswith(".icloud"):
                    note("only_in_icloud", label, rel.with_name(name[1 : -len(".icloud")]))
                continue
            if f.is_symlink():
                note("alias_or_link", label, rel)
                continue
            if not f.is_file() or name.lower() in SKIP_NAMES:
                continue
            if f.stat().st_size > (MBOX_MAX_BYTES if f.suffix.lower() == ".mbox" else MAX_BYTES):
                note("too_large", label, rel)
    return {"counts": counts, "examples": examples}


def _put_found(out: Path, data: dict) -> None:
    tmp = out / f"{FOUND_FILE}.tmp"
    tmp.write_text(json.dumps(data))
    os.replace(tmp, out / FOUND_FILE)


def write_found(a: argparse.Namespace) -> None:
    """Count what is there before reading it: files in the inbox and collections, and mail. The app shows each total as soon as it is known (the documents first: counting a big
    mailbox takes minutes)."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    connected = bool(a.mail and Path(a.mail).is_dir())
    try:
        by_folder = {"inbox": _supported(Path(a.inbox), skip=frozenset({"mail"}), out=out)}
        for name, folder in collections(a.collection):
            by_folder[name] = by_folder.get(name, 0) + (_supported(folder, out=out) if folder.is_dir() else 0)  # several folders of one category add up
        found: dict = {"documents": sum(by_folder.values()), "mail_connected": connected, "by_folder": by_folder}
        _put_found(out, found)  # the documents are known: they are shown while the mail is still being counted
        mails = _supported(Path(a.inbox) / "mail", out=out) if (Path(a.inbox) / "mail").is_dir() else 0
        attachments = 0
        if connected:
            idx = mail_index(Path(a.mail), out)
            mails += idx.mails
            attachments = len(idx.attachments)
        found.update(mails=mails, attachments=attachments)
        _put_found(out, found)
        roots = [("inbox", Path(a.inbox))] + [(name, folder) for name, folder in collections(a.collection) if folder.is_dir()]
        found["unread"] = unread_report([(n, r) for n, r in roots if r.is_dir()], out)
    except Halted:
        return  # stopped while counting: nothing more is written, nothing is read
    _put_found(out, found)


def read_everything(a: argparse.Namespace) -> dict[str, int]:
    """One round: the inbox, every collection folder, mail exports in the inbox, and Apple Mail's own folder."""
    _start_budget(Path(a.out))
    counting = threading.Thread(
        target=write_found, args=(a,), daemon=True
    )  # counting a big mailbox or iCloud takes minutes: reading starts at once and the totals appear when ready
    counting.start()
    try:
        return _read_round(a)
    finally:
        counting.join()


def _stage(out: Path, what: str, fn, *args, **kwargs) -> dict[str, int]:
    """One part of a round (the mail, a folder, the loose files). If it fails as a whole, that is counted and said, and the other parts are still read: nothing after it is lost."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - one part failing must never stop the others
        print(f"FAILED {what}: {type(e).__name__}", file=sys.stderr, flush=True)
        with _CLAIM_LOCK:
            if len(_FAILED) < MAX_FAILED:
                _FAILED.append(f"{what}: {type(e).__name__}")
        return {"parsed": 0, "skipped": 0, "failed": 1}


def _read_round(a: argparse.Namespace) -> dict[str, int]:
    out = Path(a.out)
    if (out / STOP).exists():
        return {"parsed": 0, "skipped": 0, "failed": 0}
    mails: list[dict[str, int]] = []
    documents: list[dict[str, int]] = []
    _PROGRESS.update(documents=0, mails=0, attachments=0)
    _UNREAD.update(documents=0, mails=0, attachments=0)
    _MAIL_INDEX.clear()
    _VETTED.clear()
    _write_progress(out)
    _now(out, "Mail", "looking for new messages")
    if (Path(a.inbox) / "mail").is_dir():  # the mail first, with everything it carries (mail exports dropped into the inbox: .mbox, .eml, .emlx)
        mails.append(_stage(out, "mail in the inbox", process_inbox, Path(a.inbox) / "mail", out, area="mail"))
    if a.mail and Path(a.mail).is_dir():
        mails.append(_stage(out, "the Mail folder", process_mail_store, Path(a.mail), out))
        mails.append(_stage(out, "the attachments in the Mail folder", process_mail_attachments, Path(a.mail), out))
    for name, folder in sorted(collections(a.collection), key=lambda c: priority.rank(c[0])):  # then the documents, the apps in their order
        if folder.is_dir():
            _now(out, folder.name or name, "looking for new files")
            documents.append(_stage(out, f"the {name} folder", process_inbox, folder, out, area=name))
    _now(out, "Your other files", "looking for new files")
    documents.append(_stage(out, "the inbox", process_inbox, Path(a.inbox), out, skip_folders=frozenset({"mail"})))  # then the loose files
    add = lambda parts: {k: sum(part[k] for part in parts) for k in ("parsed", "skipped", "failed")}  # noqa: E731
    return add(mails + documents)


def _wait_for_next_round(out: Path) -> None:
    """Wait until the person asks for the next round (the Documents service touches `.wake`). With ATLAS_AUTO_ROUND_SECONDS set, a round also starts by itself that often."""
    waited = 0
    while True:
        if (out / WAKE).exists():
            (out / WAKE).unlink(missing_ok=True)
            return
        if ROUND_SECONDS and waited >= ROUND_SECONDS:
            return
        time.sleep(1)
        waited += 1


if __name__ == "__main__":
    raise SystemExit(main())
