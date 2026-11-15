"""The apps that take files from the Documents app, as they declare themselves in `apps.json` (or the file `LIBRARY_APPS` points to): a name, what the app is about in words, the
words that signal a document is about it, and optionally what extra reading its files get. Nothing in the code names an app or a kind of document: the model marks each file with
the apps it is about, the order here is the order the apps are served in, and the words here decide whether a mail is worth the model's time. Add or change an app by editing the file."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

PACKAGED = Path(__file__).with_name("apps.json")
_CACHE: dict[str, tuple[float, list[App]]] = {}


@dataclass(frozen=True)
class App:
    name: str
    about: str
    terms: frozenset[str]
    reads: str = ""  # extra reading its files get after they are sorted (a name of a reader), if any


def _path() -> Path:
    return Path(os.environ.get("LIBRARY_APPS", str(PACKAGED)))


def load() -> list[App]:
    """The declared apps, in the order they are served in (read again when the file changes)."""
    path = _path()
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return []
    hit = _CACHE.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        raw = json.loads(path.read_text()).get("apps", [])
    except (OSError, ValueError, AttributeError):
        raw = []
    found = [
        App(
            name=re.sub(r"[^a-z0-9_-]", "", str(a["name"]).lower()),  # the names go into queries
            about=str(a.get("about", "")),
            terms=frozenset(str(a.get("terms", "")).lower().split()),
            reads=str(a.get("reads", "")),
        )
        for a in raw
        if isinstance(a, dict) and a.get("name")
    ]
    found = [a for a in found if a.name]
    _CACHE[str(path)] = (stamp, found)
    return found


def names() -> list[str]:
    return [a.name for a in load()]


def describe() -> dict[str, str]:
    """For the model: each app and what it is about."""
    return {a.name: a.about for a in load()}


def terms() -> frozenset[str]:
    """Every word any app declares as signalling a document about it."""
    return frozenset(w for a in load() for w in a.terms)


def reading(name: str) -> str:
    """The extra reading the files of this app get, or ''."""
    return next((a.reads for a in load() if a.name == name), "")


def with_reading(reader: str) -> list[str]:
    """The apps whose files get this extra reading."""
    return [a.name for a in load() if a.reads == reader]


def matching(text: str) -> list[str]:
    """The apps whose declared words appear in this text (for what a recogniser calls a file: no app is named in the code)."""
    words = set(re.findall(r"[^\W\d_]+", text.lower()))
    return [a.name for a in load() if a.terms & words]
