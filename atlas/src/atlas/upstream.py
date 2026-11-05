"""The atlas's own calls to the apps: is it up, and what does it find for this search. Short timeouts, run side by side, never raising."""

from __future__ import annotations

import http.client
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote

from .registry import Module

HEALTH_SECONDS = 1.5
SEARCH_SECONDS = 2.5
HEALTH_CACHE_SECONDS = 4.0
MAX_RESULTS_PER_MODULE = 8


def _get(module: Module, path: str, timeout: float, extra: dict[str, str] | None = None) -> tuple[int, bytes]:
    host, _, port = module.netloc.partition(":")
    conn = http.client.HTTPConnection(host, int(port or 80), timeout=timeout)
    try:
        conn.request("GET", path, headers={"Host": module.presented, **(extra or {})})
        response = conn.getresponse()
        return response.status, response.read(2_000_000)
    finally:
        conn.close()


class Upstreams:
    def __init__(self, modules: dict[str, Module]) -> None:
        self.modules = modules
        self._tokens: dict[str, str] = {}
        self._health: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ---- the token an app prints into its own page, which the atlas needs to use that app's API -------------------------
    def _token(self, module: Module, refresh: bool = False) -> str:
        assert module.auth is not None
        with self._lock:
            if not refresh and module.id in self._tokens:
                return self._tokens[module.id]
        status, page = _get(module, "/", HEALTH_SECONDS)
        found = re.search(rf'<meta name="{re.escape(module.auth.meta)}" content="([^"]+)"', page.decode("utf-8", "replace")) if status == 200 else None
        token = found.group(1) if found else ""
        with self._lock:
            self._tokens[module.id] = token
        return token

    def _authed_get(self, module: Module, path: str, timeout: float) -> tuple[int, bytes]:
        if module.auth is None:
            return _get(module, path, timeout)
        status, body = _get(module, path, timeout, {module.auth.header: self._token(module)})
        if status == 403:  # the app was restarted and printed a new token
            status, body = _get(module, path, timeout, {module.auth.header: self._token(module, refresh=True)})
        return status, body

    # ---- health ------------------------------------------------------------------------------------------------------
    def _check(self, module: Module) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            status, _ = _get(module, module.health, HEALTH_SECONDS)
            up = 200 <= status < 300
        except (OSError, http.client.HTTPException):
            up = False
        return {"up": up, "ms": round((time.perf_counter() - started) * 1000)}

    def health(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        stale = [m for m in self.modules.values() if m.id not in self._health or now - self._health[m.id][0] > HEALTH_CACHE_SECONDS]
        if stale:
            with ThreadPoolExecutor(max_workers=len(stale)) as pool:
                for module, result in zip(stale, pool.map(self._check, stale), strict=True):
                    self._health[module.id] = (now, result)
        return {mid: result for mid, (_, result) in self._health.items() if mid in self.modules}

    # ---- search ------------------------------------------------------------------------------------------------------
    def _search_one(self, module: Module, query: str) -> list[dict[str, Any]]:
        try:
            status, body = self._authed_get(module, f"{module.search}?q={quote(query)}", SEARCH_SECONDS)
            raw = json.loads(body).get("results", []) if status == 200 else []
        except (OSError, http.client.HTTPException, ValueError, AttributeError):
            return []
        found = []
        for item in raw[:MAX_RESULTS_PER_MODULE] if isinstance(raw, list) else []:
            if isinstance(item, dict) and item.get("title"):
                found.append(
                    {
                        "module": module.id,
                        "title": str(item["title"])[:200],
                        "subtitle": str(item.get("subtitle", ""))[:200],
                        "kind": str(item.get("kind", ""))[:40],
                        "link": str(item.get("link", ""))[:500],
                    }
                )
        return found

    def search(self, query: str) -> list[dict[str, Any]]:
        """What every searchable app finds, app by app in menu order; an app that is down or slow simply adds nothing."""
        targets = [m for m in self.modules.values() if m.search]
        if not targets or len(query.strip()) < 2:
            return []
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            lists = list(pool.map(lambda m: self._search_one(m, query), targets))
        return [item for items in lists for item in items]
