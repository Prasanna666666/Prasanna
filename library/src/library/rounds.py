"""A round of reading: what is found and what is unread, the folders walked through, and when the next round starts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import batch, bulkmail, control, extraction, mailread, priority

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


def _supported(root: Path, skip: frozenset[str] = frozenset(), only_emlx: bool = False, out: Path | None = None) -> int:
    """How many files under root the reader will take: every ordinary file with something in it that is not larger than it reads, whatever its type, so the person is shown
    the full number, not a guess."""
    total = 0
    for seen, f in enumerate(root.resolve().rglob("*"), 1):
        if out is not None and seen % control.CHECK_EVERY == 0 and control.halted(out):
            raise control.Halted
        if f.name.startswith(".") or f.is_symlink() or not f.is_file() or f.name.lower() in extraction.SKIP_NAMES:
            continue
        relative = f.relative_to(root.resolve())
        if relative.parts[0] in skip or (only_emlx and (f.suffix.lower() != ".emlx" or bulkmail._in_skipped_mailbox(relative) or bulkmail.is_bulk_mail(f))):
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
            if seen % control.CHECK_EVERY == 0 and control.halted(out):
                raise control.Halted
            name = f.name
            rel = f.relative_to(top)
            if name.startswith("."):
                if name.endswith(".icloud"):
                    note("only_in_icloud", label, rel.with_name(name[1 : -len(".icloud")]))
                continue
            if f.is_symlink():
                note("alias_or_link", label, rel)
                continue
            if not f.is_file() or name.lower() in extraction.SKIP_NAMES:
                continue
            if f.stat().st_size > (extraction.MBOX_MAX_BYTES if f.suffix.lower() == ".mbox" else extraction.MAX_BYTES):
                note("too_large", label, rel)
    return {"counts": counts, "examples": examples}


def _put_found(out: Path, data: dict) -> None:
    tmp = out / f"{FOUND_FILE}.tmp"
    batch.write_note(tmp, json.dumps(data))
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
            idx = mailread.mail_index(Path(a.mail), out)
            mails += idx.mails
            attachments = len(idx.attachments)
        found.update(mails=mails, attachments=attachments)
        _put_found(out, found)
        roots = [("inbox", Path(a.inbox))] + [(name, folder) for name, folder in collections(a.collection) if folder.is_dir()]
        found["unread"] = unread_report([(n, r) for n, r in roots if r.is_dir()], out)
    except control.Halted:
        return  # stopped while counting: nothing more is written, nothing is read
    _put_found(out, found)


def read_everything(a: argparse.Namespace) -> dict[str, int]:
    """One round: the inbox, every collection folder, mail exports in the inbox, and Apple Mail's own folder."""
    batch._start_budget(Path(a.out))
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
        with batch._CLAIM_LOCK:
            if len(batch._FAILED) < batch.MAX_FAILED:
                batch._FAILED.append(f"{what}: {type(e).__name__}")
        return {"parsed": 0, "skipped": 0, "failed": 1}


def _read_round(a: argparse.Namespace) -> dict[str, int]:
    out = Path(a.out)
    if (out / control.STOP).exists():
        return {"parsed": 0, "skipped": 0, "failed": 0}
    mails: list[dict[str, int]] = []
    documents: list[dict[str, int]] = []
    batch._PROGRESS.update(documents=0, mails=0, attachments=0)
    batch._UNREAD.update(documents=0, mails=0, attachments=0)
    mailread._MAIL_INDEX.clear()
    bulkmail._VETTED.clear()
    batch._write_progress(out)
    batch._now(out, "Mail", "looking for new messages")
    if (Path(a.inbox) / "mail").is_dir():  # the mail first, with everything it carries (mail exports dropped into the inbox: .mbox, .eml, .emlx)
        mails.append(_stage(out, "mail in the inbox", batch.process_inbox, Path(a.inbox) / "mail", out, area="mail"))
    if a.mail and Path(a.mail).is_dir():
        mails.append(_stage(out, "the Mail folder", mailread.process_mail_store, Path(a.mail), out))
        mails.append(_stage(out, "the attachments in the Mail folder", mailread.process_mail_attachments, Path(a.mail), out))
    for name, folder in sorted(collections(a.collection), key=lambda c: priority.rank(c[0])):  # then the documents, the apps in their order
        if folder.is_dir():
            batch._now(out, folder.name or name, "looking for new files")
            documents.append(_stage(out, f"the {name} folder", batch.process_inbox, folder, out, area=name))
    batch._now(out, "Your other files", "looking for new files")
    documents.append(_stage(out, "the inbox", batch.process_inbox, Path(a.inbox), out, skip_folders=frozenset({"mail"})))  # then the loose files
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
