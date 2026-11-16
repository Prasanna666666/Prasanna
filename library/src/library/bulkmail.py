"""Which mail is bulk mail and which mailboxes are not read."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import sniff


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


_VETTED: set[str] = set()  # messages already checked for being bulk mail: not opened again
