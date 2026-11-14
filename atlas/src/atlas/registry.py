"""The modules the atlas knows about: one small JSON file per module in ``modules.d``. Adding an app means dropping a file in; nothing else changes."""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SLUG = re.compile(r"^[a-z][a-z0-9-]{0,23}$")
RESERVED = frozenset({"atlas", "home", "www", "api", "static"})  # names the atlas itself uses
LOCAL_NAMES = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


class ManifestError(ValueError):
    """A module file that cannot be used; the message says which file and why."""


@dataclass(frozen=True)
class Page:
    id: str
    label: str
    icon: str = ""  # an SVG path (24x24 viewBox)


@dataclass(frozen=True)
class Auth:
    """How the atlas gets into an app's API on its own behalf (for search and health): a token the app prints into its own page."""

    meta: str  # name of the <meta> tag that holds the token
    header: str  # the header the API expects it in


@dataclass(frozen=True)
class Module:
    id: str
    name: str
    upstream: str
    app: str = ""
    tagline: str = ""
    icon: str = ""
    accent: tuple[str, str] = ("#6366f1", "#ec4899")
    health: str = "/api/health"
    search: str = ""
    scan: str = ""  # optional: a path that reads everything new (GET = status, POST = start)
    tools: str = ""  # optional: where the part lists its tools for the one assistant (GET -> {tools: [{name, description, parameters}]})
    tool: str = ""  # optional: where the assistant runs one of them (POST {name, args, user_text} -> {ok, data, error, items})
    media: str = ""  # optional: the only path prefix Atlas may fetch pictures from for this app (thumbnails in chat answers)
    home: str = ""
    items: str = ""  # optional: where the app hands over its facts as plain dated items, for Atlas to join across apps (GET -> {items: [...]})
    native: bool = False  # Atlas draws this app's page itself (it needs what several apps know)
    highlights: str = ""  # optional: where the app gives its card for the home page (GET -> {headline, sub, items, ...})
    hidden: bool = False  # works for the chat, the search and the Update, but is not an app of its own in the menu
    auth: Auth | None = None
    headers: tuple[tuple[str, str], ...] = ()  # fixed headers on Atlas's own calls (an app's change-protection header, for example)
    host: str = ""  # the Host the app is told it was called by; empty means 127.0.0.1 with its port
    pages: tuple[Page, ...] = field(default_factory=tuple)

    @property
    def netloc(self) -> str:
        """Where the atlas connects."""
        return urlsplit(self.upstream).netloc

    @property
    def presented(self) -> str:
        """What the app is told it was called as. The apps only answer their own local name, never the name the atlas reaches them by (host.docker.internal)."""
        return self.host or f"127.0.0.1:{urlsplit(self.upstream).port or 80}"

    def public(self) -> dict[str, Any]:
        """What the page is told about the module (never the upstream address)."""
        return {
            "id": self.id,
            "name": self.name,
            "app": self.app,
            "tagline": self.tagline,
            "icon": self.icon,
            "accent": list(self.accent),
            "home": self.home,
            "hidden": self.hidden,
            "native": self.native,
            "searchable": bool(self.search),
            "scannable": bool(self.scan),
            "askable": bool(self.tool),
            "pages": [{"id": p.id, "label": p.label, "icon": p.icon} for p in self.pages],
        }


def upstream_is_private(url: str) -> bool:
    """The atlas only ever talks to this computer or its private network, never the internet."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "http" or not host:
        return False
    if host in LOCAL_NAMES or host.endswith(".internal"):
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def _page(raw: Any, where: str) -> Page:
    if not isinstance(raw, dict) or not raw.get("id") or not raw.get("label"):
        raise ManifestError(f"{where}: every page needs an id and a label")
    return Page(str(raw["id"]), str(raw["label"]), str(raw.get("icon", "")))


def parse(raw: dict[str, Any], where: str) -> Module:
    """Check one module file and turn it into a Module."""
    mid = str(raw.get("id", ""))
    if not SLUG.match(mid) or mid in RESERVED:
        raise ManifestError(f"{where}: the id must be lowercase letters, digits and dashes (not {sorted(RESERVED)})")
    if not raw.get("name"):
        raise ManifestError(f"{where}: a name is needed")
    override = os.environ.get(f"ATLAS_UPSTREAM_{mid.upper().replace('-', '_')}")  # lets one machine point a module somewhere else without editing the file
    upstream = str(override or raw.get("upstream", "")).rstrip("/")
    if not upstream_is_private(upstream):
        raise ManifestError(f"{where}: the upstream must be an http address on this computer or its private network, not {upstream!r}")
    auth = raw.get("auth")
    accent = raw.get("accent") or ["#6366f1", "#ec4899"]
    return Module(
        id=mid,
        name=str(raw["name"]),
        upstream=upstream,
        app=str(raw.get("app", "")),
        tagline=str(raw.get("tagline", "")),
        icon=str(raw.get("icon", "")),
        accent=(str(accent[0]), str(accent[1])),
        health=str(raw.get("health", "/api/health")),
        search=str(raw.get("search", "")),
        scan=str(raw.get("scan", "")),
        highlights=str(raw.get("highlights", "")),
        items=str(raw.get("items", "")),
        native=raw.get("native") is True,
        tools=str(raw.get("tools", "")),
        tool=str(raw.get("tool", "")),
        media=str(raw.get("media", "")),
        headers=tuple((str(k), str(v)) for k, v in (raw.get("headers") or {}).items()),
        home=str(raw.get("home", "")),
        hidden=raw.get("hidden") is True,
        auth=Auth(str(auth["meta"]), str(auth["header"])) if isinstance(auth, dict) else None,
        host=str(raw.get("host", "")),
        pages=tuple(_page(p, where) for p in raw.get("pages", [])),
    )


def load(directory: Path) -> dict[str, Module]:
    """Every ``*.json`` in the folder, in name order. A broken file stops the start-up with a clear message (a silently missing app is worse)."""
    modules: dict[str, Module] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ManifestError(f"{path.name}: cannot be read ({exc})") from exc
        module = parse(raw, path.name)
        if module.id in modules:
            raise ManifestError(f"{path.name}: the id {module.id!r} is already used by another module")
        modules[module.id] = module
    return modules
