"""Reading a web page the owner chose, in an isolated browser (Stage 6; PRD 4.5): the owner's allowed hosts, one page at a time, as untrusted text.

The owner keeps a short list of hosts Atlas may open (stored in the Core's own folder, mode 0600). Reading a page opens it in the isolated browser worker (`browser_engine`), which can reach only those hosts, over https,
and follows no redirect off the list. What comes back is the page's visible text with its provenance, marked untrusted with no authority; a page that talks like an instruction is flagged and never obeyed
(`browser.py`). Nothing the page says can add a host, change a setting or start an action. The host must also resolve only to public addresses, so a name that points inside the owner's network is refused; the browser worker is then given THAT address and connects to it itself (TLS still verified against the host's name), so nothing resolves the name a second time and the check cannot be bypassed by changing the DNS answer between check and use.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .actions import ActionGateway
from .browser import Browser, run_browser_workflow
from .browser_engine import BrowserBlocked
from .egress import _resolve, public_address
from .errors import CoreError

HOST = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+\Z")
MAX_HOSTS = 50
MAX_TEXT = 200_000
EngineFactory = Callable[[frozenset[str], dict[str, str]], Browser]  # (the allowed hosts, each host's checked public address)


class WebReader:
    def __init__(
        self,
        data_dir: Path,
        engine: EngineFactory,
        gateway: ActionGateway,
        resolve: Callable[[str], Iterable[str]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._path, self._engine, self._gateway, self._clock = data_dir / "web-hosts.json", engine, gateway, clock
        self._resolve: Callable[[str], Iterable[str]] = resolve or self._lookup  # looked up when used, so a resolver can be swapped in tests
        self._lock = threading.Lock()

    @staticmethod
    def _lookup(host: str) -> Iterable[str]:
        return _resolve(host)

    def _public_addresses(self, host: str) -> list[str]:
        """The host's addresses if it resolves ONLY to public ones, else none."""
        found = list(self._resolve(host))
        return found if found and public_address(host, lambda _h: found) else []

    # -- the owner's list ---------------------------------------------------------------------------------------------------------------------------
    def hosts(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return {"hosts": []}
        listed = [h for h in data.get("hosts", []) if isinstance(h, str) and HOST.match(h)] if isinstance(data, dict) else []
        return {"hosts": sorted(set(listed))[:MAX_HOSTS]}

    def _save(self, hosts: list[str]) -> None:
        fd, temp = tempfile.mkstemp(dir=self._path.parent, prefix=".web-hosts-")
        with os.fdopen(fd, "w") as handle:
            json.dump({"hosts": sorted(set(hosts))}, handle)
        os.chmod(temp, 0o600)
        os.replace(temp, self._path)

    def add(self, host: str) -> dict[str, list[str]]:
        name = host.strip().lower()
        if not HOST.match(name) or not public_address(name, self._resolve):
            raise CoreError("invalid_request")  # a name that does not exist, or points inside the owner's network, is never listed
        with self._lock:
            current = self.hosts()["hosts"]
            if len(current) >= MAX_HOSTS and name not in current:
                raise CoreError("conflict")
            self._save([*current, name])
        return self.hosts()

    def remove(self, host: str) -> dict[str, list[str]]:
        with self._lock:
            self._save([h for h in self.hosts()["hosts"] if h != host.strip().lower()])
        return self.hosts()

    # -- reading ----------------------------------------------------------------------------------------------------------------------------------
    def read(self, url: str) -> dict[str, object]:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or host not in self.hosts()["hosts"] or parts.username or parts.password:
            raise CoreError("forbidden")  # only a listed host, over https, with no credentials in the address
        addresses = self._public_addresses(host)
        if not addresses:
            raise CoreError("forbidden")
        browser: Browser | None = None
        try:
            browser = self._engine(frozenset({host}), {host: addresses[0]})  # the browser is told this address and does no lookup of its own
            result = run_browser_workflow(browser, [("open", url)], allowed_hosts=frozenset({host}), gateway=self._gateway)
        except BrowserBlocked as blocked:
            raise CoreError("timeout" if blocked.code in ("worker_stopped", "navigation_failed") else "forbidden") from None
        finally:
            close = getattr(browser, "close", None) if browser is not None else None
            if callable(close):
                close()
        if result.status != "completed" or not result.pages:
            raise CoreError("forbidden" if result.status == "blocked" else "timeout")
        page = result.pages[0]
        text = page.text[:MAX_TEXT]
        return {
            "url": page.url,
            "domain": host,
            "retrieved_at": self._clock().isoformat(),
            "content_hash": hashlib.sha256(page.text.encode()).hexdigest(),
            "text": text,
            "truncated": len(page.text) > MAX_TEXT,
            "injection_flags": ["instruction_like_text"] if page.instruction_like else [],
            "trust": page.trust,
            "authority": page.authority,
        }
