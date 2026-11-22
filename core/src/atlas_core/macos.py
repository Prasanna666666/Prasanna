"""The macOS-side providers a real Core needs: Keychain secrets, the Keychain rollback anchor, the folder-permission probe and the Apple Mail reader.

Everything here is written to be exercised on Linux (the Keychain commands go through an injectable runner, the permission probe and the mail reader work on ordinary folders and
synthetic `.emlx` files) and is **UNVERIFIED on a Mac**: the real `security` tool, the real TCC behaviour and a real Mail store have never been touched. Nothing here reads a real
mailbox in CI.
"""

from __future__ import annotations

import email.policy
import email.utils
import getpass
import hashlib
import json
import os
import re
import secrets
import shlex
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
        return str(done.stdout).strip()

    def write(self, service: str, value: str) -> None:
        command = f"add-generic-password -U -a {shlex.quote(self._account)} -s {shlex.quote(service)} -w {shlex.quote(value)}\n"
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
    on every call and caches nothing. UNVERIFIED on a Mac; verified on Linux with folders whose mode forbids listing."""

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


class EmlxMailbox:
    """The Apple Mail reader (the `Mailbox` the mail index takes): a folder of `.emlx` files, read-only, symlinks never followed.

    It returns ONLY the five stored fields (identity, sender, date, subject, plain-text body). Attachments are never decoded or opened: only text/plain parts of the message are read.
    Listing is newest-first by file modification time and paged; the order is a hope, never relied on by the Core. UNVERIFIED against a real Mail store (the format is handled
    from its documentation: a byte count line, that many bytes of RFC 822 message, then a property list that is ignored)."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._cache: list[tuple[str, str, float, Path]] = []
        self._by_id: dict[str, Path] = {}
        self._lock = threading.Lock()

    def _scan(self) -> None:
        found: dict[str, tuple[float, str, Path]] = {}
        for folder, _directories, files in os.walk(self._root, followlinks=False):  # a linked folder is listed by walk but never entered
            for name in files:
                if not name.endswith(".emlx"):
                    continue
                path = Path(folder) / name
                try:
                    st = path.lstat()
                except OSError:
                    continue
                if path.is_symlink() or not path.is_file():
                    continue
                identity = self._identity(path)
                known = found.get(identity)
                if known is None or st.st_mtime > known[0]:
                    found[identity] = (st.st_mtime, f"{st.st_size}-{st.st_mtime_ns}", path)
        ordered = sorted(found.items(), key=lambda kv: (-kv[1][0], kv[0]))
        with self._lock:
            self._cache = [(identity, version, mtime, path) for identity, (mtime, version, path) in ordered]
            self._by_id = {identity: path for identity, _, _, path in self._cache}

    def _identity(self, path: Path) -> str:
        """The Message-ID header (made safe), else a name made from the file's place under the root."""
        try:
            with path.open("rb") as handle:
                head = handle.read(MAX_HEADER_BYTES)
            line, _, rest = head.partition(b"\n")
            message = message_from_bytes(rest[: int(line.strip() or 0)] if line.strip().isdigit() else rest, policy=email.policy.default)
            raw = str(message.get("Message-ID", "")).strip()
        except (OSError, ValueError, LookupError):
            raw = ""
        cleaned = _UNSAFE.sub("_", raw)[:200]
        if cleaned and _ID.match(cleaned):
            return cleaned
        rel = str(path.relative_to(self._root)) if path.is_relative_to(self._root) else path.name
        return "emlx." + hashlib.sha256(rel.encode()).hexdigest()[:24]

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
            path = self._by_id.get(message_id)
        if path is None:
            self._scan()
            with self._lock:
                path = self._by_id.get(message_id)
        return None if path is None else self._parse(message_id, path)

    def _parse(self, message_id: str, path: Path) -> dict[str, Any] | None:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                data = handle.read(MAX_EMLX_BYTES + 1)
        except OSError:
            return None
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
