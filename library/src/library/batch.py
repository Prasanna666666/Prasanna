"""Reading a folder of files in batches: claiming, writing what was found, taking mail apart, counting what could not be read."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import bulkmail, control, extraction, flags, readers, sniff


def _done(out: Path, digest: str) -> bool:
    """Has this content been read? A marker with no content in it is kept, because the readable copy is deleted once the app has stored it."""
    return (out / ".done" / digest).exists() or (out / f"{digest}.json").exists()


def _write(out: Path, digest: str, label: str, size: int, res: dict, area: str, source: str = "") -> None:
    doc = {
        "schema": extraction.SCHEMA,
        "sha256": digest,
        "name": extraction.clean(label)[:255],
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
    digest = extraction.sha256(f)
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
        for name, content in (readers.read_emlx(f) if extraction._is_emlx(f) else readers.read_eml(f))[1]:
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
    if size <= (extraction.MBOX_MAX_BYTES if kind == "mbox" else extraction.MAX_BYTES):
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
    if f.name.lower() in extraction.SKIP_NAMES or size == 0 or size > extraction.MBOX_MAX_BYTES:
        counts["skipped"] += 1
        return
    try:
        kind = sniff.kind_of(f)
    except (OSError, ValueError):
        kind = "binary"
    if bulkmail._is_bulk_message(f, kind, area, depth) or _too_large(size, kind, label, counts):
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
            extraction.extract_isolated(f) if isolated and kind != "email" else extraction.extract(f)
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
    target = folder / f"{extraction.sha256(f)}{f.suffix.lower()}"
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
    while (out / control.PAUSE).exists() and not (out / control.STOP).exists():
        time.sleep(1)
    time.sleep(control.GENTLE_SECONDS)
    left = _BUDGET["left"]
    if left is not None and left <= 0:
        (out / flags.AUTO_CAPPED).touch()
        return True
    return (out / control.STOP).exists()


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
        and f.name.lower() not in extraction.SKIP_NAMES
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
