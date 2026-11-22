"""The macOS-side providers a real Core needs: Keychain secrets, the Keychain rollback anchor, the folder-permission probe and the Apple Mail reader.

Everything here is written to be exercised on Linux (the Keychain commands go through an injectable runner, the permission probe and the mail reader work on ordinary folders and
synthetic `.emlx` files) and is also exercised on a GitHub-hosted macOS runner against the real `security`/Keychain (`tests/test_macos_native.py`). **Still unverified anywhere:** the real TCC behaviour and prompts, and a
real Apple Mail store. Nothing here reads a real mailbox in CI.
"""

from __future__ import annotations

import base64
import email.policy
import email.utils
import getpass
import hashlib
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from email import message_from_bytes
from pathlib import Path
from typing import Any

from .access import GRANTED, MISSING, UNKNOWN, PermissionEvidence
from .designation import AnchorRecord, Intent, Pending, RecordAnchor
from .mail import _ID, MAX_BODY_CHARS, Listed, ListPage

SECURITY_TOOL = "security"
NOT_FOUND = 44  # `security` exit status for a missing item
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


_PLAIN = re.compile(r"[A-Za-z0-9._-]+")
_ENCODED = "b64:"


def _encode(value: str) -> str:
    """What reaches `security -i`. Its command parser is not a shell's (a real macOS run showed single quotes and `$` in a value break it), so a value is sent as is only if it is
    made of letters, digits, `.`, `_` and `-` (the hex store keys); anything else travels as `b64:` plus base64 and is decoded on read."""
    if _PLAIN.fullmatch(value) and not value.startswith(_ENCODED):
        return value
    return _ENCODED + base64.b64encode(value.encode()).decode()


def _decode(stored: str) -> str:
    if stored.startswith(_ENCODED):
        try:
            return base64.b64decode(stored[len(_ENCODED) :], validate=True).decode()
        except (ValueError, UnicodeDecodeError):
            raise KeychainError("decode") from None
    return stored


class KeychainError(Exception):
    """The Keychain could not be read or written. Carries no secret and no output of the tool."""


class KeychainItems:
    """Generic-password items, one per name, via the `security` tool. Values travel to `security -i` on standard input, never on a command line."""

    def __init__(self, account: str | None = None, runner: Runner = subprocess.run) -> None:
        self._account, self._run = account or getpass.getuser(), runner

    def read(self, service: str) -> str | None:
        done = self._run([SECURITY_TOOL, "find-generic-password", "-a", self._account, "-s", service, "-w"], capture_output=True, text=True, check=False)
        if done.returncode == NOT_FOUND:
            return None
        if done.returncode != 0:
            raise KeychainError("read")
        return _decode(str(done.stdout).strip())

    def write(self, service: str, value: str) -> None:
        command = f"add-generic-password -U -a {shlex.quote(self._account)} -s {shlex.quote(service)} -w {_encode(value)}\n"
        done = self._run([SECURITY_TOOL, "-i"], input=command, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise KeychainError("write")

    def delete(self, service: str) -> None:
        done = self._run([SECURITY_TOOL, "delete-generic-password", "-a", self._account, "-s", service], capture_output=True, text=True, check=False)
        if done.returncode not in (0, NOT_FOUND):
            raise KeychainError("delete")

    def secret(self, name: str) -> str:
        """A 256-bit key of its own for each store (never shared), created on first use."""
        service = f"atlas-{name}"
        found = self.read(service)
        if found:
            return found
        fresh = secrets.token_hex(32)
        self.write(service, fresh)
        if self.read(service) != fresh:  # another process may have created it first: use what is really stored
            raise KeychainError("verify")
        return fresh


class KeychainAnchor(RecordAnchor):
    """The designation store's rollback anchor kept OUTSIDE its database, in a Keychain item. One small JSON record; the two-phase rules are `RecordAnchor`'s."""

    SERVICE = "atlas-designation-anchor"

    def __init__(self, items: KeychainItems) -> None:
        super().__init__()
        self._items = items

    def _load(self) -> AnchorRecord | None:
        try:
            raw = self._items.read(self.SERVICE)
        except KeychainError:
            raise OSError("anchor unavailable") from None
        if not raw:
            return None
        row = json.loads(raw)
        pending = row.get("pending")
        intent = pending.get("intent") if pending else None
        return AnchorRecord(
            row["seq"],
            row["head"],
            Pending(pending["seq"], pending["head"], Intent(intent["source_type"], intent["reason"], intent.get("request_id")) if intent else None)
            if pending
            else None,
        )

    def _save(self, record: AnchorRecord | None) -> None:
        try:
            if record is None:
                self._items.delete(self.SERVICE)
                return
            pending = record.pending
            row: dict[str, Any] = {"seq": record.seq, "head": record.head, "pending": None}
            if pending is not None:
                intent = pending.intent
                row["pending"] = {
                    "seq": pending.seq, "head": pending.head,
                    "intent": None if intent is None else {"source_type": intent.source_type, "reason": intent.reason, "request_id": intent.request_id},
                }  # fmt: skip
            self._items.write(self.SERVICE, json.dumps(row, separators=(",", ":")))
        except KeychainError:
            raise OSError("anchor unavailable") from None


class FolderPermissions:
    """The platform-permission provider, by probing: can this process actually list the folder? On macOS a folder the user has not allowed (TCC) fails with EPERM, so a listable folder is
    evidence of access and a refusal is evidence of its absence; a folder that is not there, or any other error, is no evidence at all (`unknown`). It asks the operating system fresh
    on every call and caches nothing. Verified on Linux with folders whose mode forbids listing; real TCC decisions (Documents, Full Disk Access for Mail) have never been observed."""

    def __init__(self, folders: dict[str, Path], clock: Callable[[], datetime] | None = None) -> None:
        self._folders = folders
        self._clock = clock or (lambda: datetime.now(UTC))

    def current(self, source_type: str) -> PermissionEvidence:
        path, state = self._folders.get(source_type), UNKNOWN
        if path is not None:
            try:
                with os.scandir(path):
                    state = GRANTED
            except PermissionError:
                state = MISSING
            except OSError:
                state = UNKNOWN
        return PermissionEvidence(source_type, state, self._clock())


_UNSAFE = re.compile(r"[^A-Za-z0-9._@<>+=-]")
MAX_HEADER_BYTES = 64 * 1024
MAX_EMLX_BYTES = 8 * 1024 * 1024  # a larger message is not read (it is reported as unreadable, never truncated)


Parts = tuple[str, ...]  # a file's place under the Mail root, one name per directory level (never a path that is reopened)


def _open_dir_nofollow(name: str, dir_fd: int | None = None) -> int:
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)


def open_confined(root_fd: int, parts: Parts) -> int:
    """Open a regular file by walking `parts` from the pinned root descriptor, every directory and the file itself opened relative to the previous
    descriptor with O_NOFOLLOW: a symlink (or a directory replaced by one) at ANY level fails with OSError instead of leading outside the root.
    The caller reads from the returned descriptor and never reopens the name. A non-regular file (a FIFO, a device) is refused without blocking."""
    held = os.dup(root_fd)
    try:
        for name in parts[:-1]:
            nxt = _open_dir_nofollow(name, held)
            os.close(held)
            held = nxt
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=held)
    finally:
        os.close(held)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError("not a regular file")
    return fd


class EmlxMailbox:
    """The Apple Mail reader (the `Mailbox` the mail index takes): a folder of `.emlx` files, read-only, symlinks never followed at any level.

    Every operation pins the Mail root with a directory descriptor and reaches a message only by walking its directories and opening the file relative to that
    descriptor with O_NOFOLLOW at every step (`open_confined`); the message's identity and its body are read from the very descriptor that was opened, and a name is
    never validated and then reopened. A file or a parent directory swapped for a symlink between discovery and open therefore fails closed (the item is skipped or
    reads as missing); nothing outside the root is ever read, identified or indexed. (The designated root's own ancestors are the owner's designation, not walked here.)

    It returns ONLY the five stored fields (identity, sender, date, subject, plain-text body). Attachments are never decoded or opened: only text/plain parts of the message are read.
    Listing is newest-first by file modification time and paged; the order is a hope, never relied on by the Core. Not yet exercised against a real Mail store (the format is handled
    from its documentation: a byte count line, that many bytes of RFC 822 message, then a property list that is ignored)."""

    _before_open: Callable[[str, Parts], None] | None = None  # test seam: called just before each confined open (a race is staged here); None in production

    def __init__(self, root: Path) -> None:
        self._root = root
        self._cache: list[tuple[str, str, float, Parts]] = []
        self._by_id: dict[str, Parts] = {}
        self._lock = threading.Lock()

    def _pin_root(self) -> int:
        return _open_dir_nofollow(os.fspath(self._root))

    def _candidates(self, root_fd: int) -> list[Parts]:
        """Every `.emlx` name under the pinned root, found by listing directory descriptors (a linked folder or file is never entered or listed)."""
        found: list[Parts] = []
        pending: list[tuple[Parts, int]] = [((), os.dup(root_fd))]
        try:
            while pending:
                parts, fd = pending.pop()
                try:
                    with os.scandir(fd) as entries:
                        names = [(e.name, e.is_dir(follow_symlinks=False), e.is_file(follow_symlinks=False)) for e in entries]
                except OSError:
                    names = []
                finally:
                    os.close(fd)
                for name, is_dir, is_file in names:
                    if is_dir:
                        try:
                            child = self._open_dir(root_fd, (*parts, name))
                        except OSError:
                            continue
                        pending.append(((*parts, name), child))
                    elif is_file and name.endswith(".emlx"):
                        found.append((*parts, name))
        finally:
            for _, fd in pending:
                os.close(fd)
        return found

    def _open_dir(self, root_fd: int, parts: Parts) -> int:
        held = os.dup(root_fd)
        try:
            for name in parts:
                nxt = _open_dir_nofollow(name, held)
                os.close(held)
                held = nxt
        except OSError:
            os.close(held)
            raise
        return held

    def _open(self, root_fd: int, parts: Parts) -> int:
        hook = self._before_open
        if hook is not None:
            hook("open", parts)
        return open_confined(root_fd, parts)

    def _scan(self) -> None:
        found: dict[str, tuple[float, str, Parts]] = {}
        try:
            root_fd = self._pin_root()
        except OSError:
            root_fd = -1
        if root_fd >= 0:
            try:
                for parts in self._candidates(root_fd):
                    try:
                        fd = self._open(root_fd, parts)
                    except OSError:
                        continue  # replaced by a link, vanished, or not a regular file: not listed
                    with os.fdopen(fd, "rb") as handle:
                        st = os.fstat(handle.fileno())
                        identity = self._identity(handle.read(MAX_HEADER_BYTES), parts)
                    known = found.get(identity)
                    if known is None or st.st_mtime > known[0]:
                        found[identity] = (st.st_mtime, f"{st.st_size}-{st.st_mtime_ns}", parts)
            finally:
                os.close(root_fd)
        ordered = sorted(found.items(), key=lambda kv: (-kv[1][0], kv[0]))
        with self._lock:
            self._cache = [(identity, version, mtime, parts) for identity, (mtime, version, parts) in ordered]
            self._by_id = {identity: parts for identity, _, _, parts in self._cache}

    @staticmethod
    def _identity(head: bytes, parts: Parts) -> str:
        """The Message-ID header (made safe), else a name made from the file's place under the root. Uses only bytes already read from the opened descriptor."""
        try:
            line, _, rest = head.partition(b"\n")
            message = message_from_bytes(rest[: int(line.strip() or 0)] if line.strip().isdigit() else rest, policy=email.policy.default)
            raw = str(message.get("Message-ID", "")).strip()
        except (ValueError, LookupError):
            raw = ""
        cleaned = _UNSAFE.sub("_", raw)[:200]
        if cleaned and _ID.match(cleaned):
            return cleaned
        return "emlx." + hashlib.sha256(os.sep.join(parts).encode()).hexdigest()[:24]

    def list_page(self, cursor: str | None, limit: int) -> ListPage:
        if cursor is None:
            self._scan()
        start = int(cursor or 0)
        with self._lock:
            window = self._cache[start : start + limit]
            total = len(self._cache)
        items = [Listed(identity, version, datetime.fromtimestamp(mtime, UTC).isoformat()) for identity, version, mtime, _ in window]
        end = start + limit
        return ListPage(items, str(end) if end < total else None)

    def read(self, message_id: str) -> dict[str, Any] | None:
        with self._lock:
            parts = self._by_id.get(message_id)
        if parts is None:
            self._scan()
            with self._lock:
                parts = self._by_id.get(message_id)
        return None if parts is None else self._parse(message_id, parts)

    def _parse(self, message_id: str, parts: Parts) -> dict[str, Any] | None:
        try:
            root_fd = self._pin_root()
        except OSError:
            return None
        try:
            fd = self._open(root_fd, parts)
            with os.fdopen(fd, "rb") as handle:
                data = handle.read(MAX_EMLX_BYTES + 1)
        except OSError:
            return None
        finally:
            os.close(root_fd)
        if len(data) > MAX_EMLX_BYTES:
            return None
        line, _, rest = data.partition(b"\n")
        if not line.strip().isdigit():
            return None
        message = message_from_bytes(rest[: int(line.strip())], policy=email.policy.default)
        body_part = message.get_body(preferencelist=("plain",))  # only a text/plain part: attachments are never decoded
        try:
            body = body_part.get_content() if body_part is not None else ""
            stamp = email.utils.parsedate_to_datetime(str(message.get("Date")))
        except (LookupError, ValueError, TypeError):
            return None
        return {
            "message_id": message_id,
            "sender": str(message.get("From", "")).strip(),
            "date": (stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)).isoformat(),
            "subject": str(message.get("Subject", "")).strip(),
            "body": str(body)[: MAX_BODY_CHARS + 1],
        }
