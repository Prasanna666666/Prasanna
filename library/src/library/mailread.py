"""Reading mail: the index of what was seen, and a mailbox or the attachments of its messages, round by round."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from . import batch, bulkmail, control

_MAIL_INDEX: dict[str, MailIndex] = {}


_INDEX_LOCK = threading.Lock()


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


class _HashedSeen:
    """What the reader remembers of mail it has seen. The keys are the mail files' relative paths, which name mailboxes and accounts, so they are kept only as one-way hashes: the reader can still ask "have I seen this?" and the volume no longer holds the paths. (The reader must read this back itself, so it cannot be sealed to a public key.)"""

    def __init__(self, stored: dict[str, str] | None = None) -> None:
        self.stored: dict[str, str] = dict(stored or {})  # hashed key -> stamp: this is what is written to the volume

    @staticmethod
    def _h(key: str) -> str:
        return hashlib.sha256(str(key).encode()).hexdigest()[:32]

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.stored.get(self._h(key), default)

    def __setitem__(self, key: str, value: str) -> None:
        self.stored[self._h(key)] = value

    def update(self, other: dict[str, str]) -> None:
        for key, value in other.items():
            self[key] = value


def _seen_cache(out: Path, root: Path, kind: str = "") -> tuple[Path, _HashedSeen]:
    cache_file = out / ".mailseen-3" / (hashlib.sha256((kind + str(root)).encode()).hexdigest()[:16] + ".json")
    try:
        return cache_file, _HashedSeen(json.loads(cache_file.read_text()) if cache_file.exists() else {})
    except (OSError, ValueError):
        return cache_file, _HashedSeen()


def _build_mail_index(root: Path, out: Path) -> MailIndex:
    idx = MailIndex()
    _, seen = _seen_cache(out, root)
    bulk_owners: set[tuple[str, str]] = set()
    candidates: list[tuple[Path, str, tuple[str, str]]] = []
    for n, f in enumerate(root.rglob("*"), 1):  # one look at every file, not sorted first, so Pause and Stop are heard during the walk
        if n % control.CHECK_EVERY == 0:
            batch._now(out, "Mail", f"looking for new messages ({n:,} looked at)")
            if control.halted(out):
                raise control.Halted
        if f.name.startswith(".") or f.is_symlink():
            continue
        inside = f.relative_to(root)
        if bulkmail._in_skipped_mailbox(inside):
            continue
        if f.suffix.lower() == ".emlx":
            stat = f.stat()
            stamp, key = f"{stat.st_size}:{int(stat.st_mtime)}", str(inside)
            owner = (str(f.parent), f.name.split(".")[0])
            if seen.get(key) == f"bulk:{stamp}":
                bulk_owners.add(owner)
            elif seen.get(key) == stamp:
                idx.gone += 1
            elif bulkmail.is_bulk_mail(f):
                idx.new_bulk[key] = stamp
                bulk_owners.add(owner)
            else:
                idx.messages.append((f, key, stamp))
                bulkmail._VETTED.add(str(f))
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
    except control.Halted:
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
    batch._progress_add(out, "mail", gone, "attachments")
    for i in range(0, len(todo), batch.BATCH):
        chunk = todo[i : i + batch.BATCH]
        for k, v in batch._read_batch([f for f, _, _ in chunk], lambda f: "/".join(f.parts[-3:]), out, "mail", isolated, group="attachments").items():
            counts[k] += v
        for _f, relative, stamp in chunk:
            seen[relative] = stamp
        bulkmail._save_seen(cache_file, seen)
        if batch.checkpoint(out):
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
    except control.Halted:
        return counts  # stopped while looking through the mail folder
    cache_file, seen = _seen_cache(out, root)
    seen.update({k: f"bulk:{v}" for k, v in idx.new_bulk.items()})  # remembered, so their headers are not read again
    batch._progress_add(out, "mail", idx.gone)
    for i in range(
        0, len(idx.messages), batch.BATCH
    ):  # a batch at a time, several messages at once; what is done is remembered after each batch, so an interrupted first read carries on
        chunk = idx.messages[i : i + batch.BATCH]
        for k, v in batch._read_batch([f for f, _, _ in chunk], lambda f: f.name, out, "mail", isolated).items():
            counts[k] += v
        for _f, relative, stamp in chunk:
            seen[relative] = stamp
        bulkmail._save_seen(cache_file, seen)
        if batch.checkpoint(out):
            break
    bulkmail._save_seen(cache_file, seen)
    return counts
