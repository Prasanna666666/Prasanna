"""The atlas's own calls to the apps: is it up, and what does it find for this search. Short timeouts, run side by side, never raising."""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote, urlsplit

from kit.sign import sign

from .registry import Module

HEALTH_SECONDS = 1.5
SEARCH_SECONDS = 2.5
HEALTH_CACHE_SECONDS = 4.0
MAX_RESULTS_PER_MODULE = 8
SCAN_SECONDS = 6.0
ASK_SECONDS = 60.0
FAST_SECONDS = 3.0
MAX_BODY = 8_000_000


def _call(module: Module, method: str, path: str, timeout: float, *, extra: dict[str, str] | None = None, body: bytes = b"") -> tuple[int, bytes, str]:
    host, _, port = module.netloc.partition(":")
    conn = http.client.HTTPConnection(host, int(port or 80), timeout=timeout)
    headers = {"Host": module.presented, **dict(module.headers), **(extra or {}), **sign(method, path)}
    if method == "POST":
        headers["Content-Length"] = str(len(body))
        if body:
            headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, headers=headers, body=body or None)
        response = conn.getresponse()
        return response.status, response.read(MAX_BODY), response.getheader("Content-Type", "")
    finally:
        conn.close()


def _get(module: Module, path: str, timeout: float, extra: dict[str, str] | None = None) -> tuple[int, bytes]:
    status, body, _ = _call(module, "GET", path, timeout, extra=extra)
    return status, body


def _build_of(body: bytes) -> str:
    """Which version of the app answered (its own words, trimmed): so a part that was not updated can be seen."""
    try:
        raw = json.loads(body).get("build", "")
    except (ValueError, AttributeError):
        return ""
    return str(raw)[:12] if isinstance(raw, str) else ""


class Upstreams:
    def __init__(self, modules: dict[str, Module]) -> None:
        self.modules = modules
        self._tokens: dict[str, str] = {}
        self._health: dict[str, tuple[float, dict[str, Any]]] = {}
        self._last_scan: dict[str, dict[str, Any]] = {}  # what each app last said about its reading
        self._lock = threading.Lock()

    # ---- the token an app prints into its own page, which the atlas needs to use that app's API -------------------------
    def _token(self, module: Module, refresh: bool = False) -> str:
        if module.auth is None:
            raise RuntimeError(f"{module.name} has no token set-up")
        with self._lock:
            if not refresh and module.id in self._tokens:
                return self._tokens[module.id]
        status, page = _get(module, "/", HEALTH_SECONDS)
        found = re.search(rf'<meta name="{re.escape(module.auth.meta)}" content="([^"]+)"', page.decode("utf-8", "replace")) if status == 200 else None
        token = found.group(1) if found else ""
        with self._lock:
            self._tokens[module.id] = token
        return token

    def _authed_full(self, module: Module, method: str, path: str, timeout: float, body: bytes = b"") -> tuple[int, bytes, str]:
        if module.auth is None:
            return _call(module, method, path, timeout, body=body)
        result = _call(module, method, path, timeout, extra={module.auth.header: self._token(module)}, body=body)
        if result[0] == 403:  # the app was restarted and printed a new token
            result = _call(module, method, path, timeout, extra={module.auth.header: self._token(module, refresh=True)}, body=body)
        return result

    def _authed(self, module: Module, method: str, path: str, timeout: float) -> tuple[int, bytes]:
        status, body, _ = self._authed_full(module, method, path, timeout)
        return status, body

    def _authed_get(self, module: Module, path: str, timeout: float) -> tuple[int, bytes]:
        return self._authed(module, "GET", path, timeout)

    # ---- health ------------------------------------------------------------------------------------------------------
    def _check(self, module: Module) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            status, body = _get(module, module.health, HEALTH_SECONDS)
            up = 200 <= status < 300
        except (OSError, http.client.HTTPException):
            up, body = False, b""
        return {"up": up, "ms": round((time.perf_counter() - started) * 1000), "build": _build_of(body)}

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

    # ---- one Update button: read everything new, in every app that can -----------------------------------------------
    def _scan_one(self, module: Module, start: bool) -> dict[str, Any]:
        down = {
            "up": False,
            "running": False,
            "progress": "",
            "summary": "",
            "problems": [f"{module.name} is not running"],
            "needs_check": 0,
            "parts": [],
            "paused": False,
            "stopping": False,
        }
        try:
            if start:
                self._authed(module, "POST", module.scan, SCAN_SECONDS)
            status, body = self._authed(module, "GET", module.scan, SCAN_SECONDS)
            raw = json.loads(body) if status == 200 else None
        except TimeoutError:
            # it did not answer in time: busy with a big job, not switched off. The last thing it said is kept, so the panel does not flicker to "switched off"
            last = self._last_scan.get(module.id)
            return {**last, "progress": "busy, still working…"} if last else {**down, "up": True, "problems": []}
        except (OSError, http.client.HTTPException, ValueError):
            return down
        if not isinstance(raw, dict):
            return down
        report = {
            "up": True,
            "running": bool(raw.get("running")),
            "progress": str(raw.get("progress", ""))[:200],
            "summary": str(raw.get("summary", ""))[:200],
            "problems": [str(p)[:300] for p in (raw.get("problems") or [])][:5],
            "needs_check": int(raw.get("needs_check") or 0),
            "parts": self._parts(raw.get("parts")),
            "paused": raw.get("paused") is True,
            "stopping": raw.get("stopping") is True,
        }
        self._last_scan[module.id] = report
        return report

    @staticmethod
    def _parts(raw: Any) -> list[dict[str, str]]:
        """The rows an app wants the Update to show (Documents, Pictures, Mails), checked: a name and a short line each."""
        if not isinstance(raw, list):
            return []
        return [{"name": str(p["name"])[:30], "detail": str(p.get("detail", ""))[:200]} for p in raw[:6] if isinstance(p, dict) and p.get("name")]

    def control(self, action: str) -> dict[str, Any]:
        """Pause, resume or stop the reading that is running, in every app that supports it (an app that does not simply ignores it)."""
        if action not in ("pause", "resume", "stop"):
            return self.scan()
        for module in (m for m in self.modules.values() if m.scan):
            with contextlib.suppress(OSError, http.client.HTTPException, ValueError):
                self._authed(module, "POST", f"{module.scan}/{action}", SCAN_SECONDS)
        return self.scan()

    @staticmethod
    def _card(raw: Any) -> dict[str, Any] | None:
        """One app's card for the home page, checked and trimmed: short strings, a few rows, picture numbers, and a link inside the app."""
        if not isinstance(raw, dict) or not raw.get("headline"):
            return None
        card: dict[str, Any] = {k: str(raw.get(k, ""))[:80] for k in ("headline", "sub", "tone")}
        card["note"] = str(raw.get("note", ""))[:140]
        card["link"] = str(raw.get("link", ""))[:80] if str(raw.get("link", "")).startswith("#") else ""
        if isinstance(raw.get("figure"), int):
            card["figure"] = raw["figure"]
        card["items"] = [
            {"label": str(i.get("label", ""))[:60], "value": str(i.get("value", ""))[:40], "kind": str(i.get("kind", ""))[:20]}
            for i in (raw.get("items") or [])[:6]
            if isinstance(i, dict)
        ]
        card["images"] = [i for i in (raw.get("images") or [])[:6] if isinstance(i, int)]
        return card

    def home(self) -> dict[str, Any]:
        """The home page: each app's card, fetched at the same time; an app that is down or slow just has no card."""
        targets = [m for m in self.modules.values() if m.highlights]

        def one(module: Module) -> dict[str, Any] | None:
            try:
                status, body = self._authed(module, "GET", module.highlights, HEALTH_SECONDS * 2)
                return self._card(json.loads(body)) if status == 200 else None
            except (OSError, http.client.HTTPException, ValueError):
                return None

        if not targets:
            return {"cards": {}, "builds": {}}
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            cards = list(pool.map(one, targets))
        health = self.health()
        builds = {"atlas": os.environ.get("ATLAS_BUILD", "unknown")[:12], **{m: h["build"] for m, h in health.items() if h.get("build")}}
        return {"cards": {m.id: c for m, c in zip(targets, cards, strict=True) if c is not None}, "builds": builds}

    def auto(self) -> dict[str, Any]:
        """The idle check on this computer asks every app that can read by itself to do so. Each app decides for itself whether the amount waiting is small enough
        (the Documents service reads automatically only when fewer than 50 files are waiting); one that cannot, or is down, is simply left out."""
        answers: dict[str, Any] = {}
        for module in (m for m in self.modules.values() if m.scan):
            with contextlib.suppress(OSError, http.client.HTTPException, ValueError):
                status, body = self._authed(module, "POST", f"{module.scan}/auto", SCAN_SECONDS)
                if status == 200 and isinstance(reply := json.loads(body), dict):
                    answers[module.id] = {k: reply[k] for k in ("started", "reason", "waiting", "limit") if k in reply}
        return {"modules": answers}

    def scan(self, start: bool = False) -> dict[str, Any]:
        """Start (or just read) the update of every app that supports it; one app being down never stops the others."""
        targets = [m for m in self.modules.values() if m.scan]
        if not targets:
            return {"running": False, "modules": {}}
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            results = list(pool.map(lambda m: self._scan_one(m, start), targets))
        modules = {m.id: {"name": m.name, **r} for m, r in zip(targets, results, strict=True)}
        return {"running": any(r["running"] for r in results), "modules": modules}

    # ---- the one AI model all apps share (Ollama on this computer) -----------------------------------------------------
    def ai(self, model_url: str) -> dict[str, Any]:
        """Is the shared model server up, and which models does it hold? Atlas only looks; the apps are the ones that use it."""
        if not model_url:
            return {"configured": False, "up": False, "models": []}
        parts = urlsplit(model_url)
        probe = Module(id="model", name="AI model", upstream=model_url, host=f"127.0.0.1:{parts.port or 11434}")
        try:
            status, body = _get(probe, "/api/tags", HEALTH_SECONDS)
            models = [str(m.get("name", "")) for m in json.loads(body).get("models", []) if isinstance(m, dict)] if status == 200 else []
        except (OSError, http.client.HTTPException, ValueError, AttributeError):
            return {"configured": True, "up": False, "models": []}
        return {"configured": True, "up": status == 200, "models": [m for m in models if m][:8]}

    # ---- the single chat: one question to one app, and a picture from an app ------------------------------------------
    def tool_specs(self, module: Module) -> list[dict[str, Any]]:
        """The tools this part of the app offers (name, description, parameters), checked. [] if it offers none or is not running."""
        if not module.tools:
            return []
        try:
            status, body = self._authed_get(module, module.tools, ASK_SECONDS)
            raw = json.loads(body)
        except (OSError, http.client.HTTPException, ValueError):
            return []
        found = raw.get("tools") if status == 200 and isinstance(raw, dict) else None
        return [
            t
            for t in (found or [])
            if isinstance(t, dict) and re.fullmatch(r"[a-z][a-z0-9_]{0,60}", str(t.get("name", ""))) and isinstance(t.get("parameters"), dict)
        ]

    def call_tool(self, module: Module, name: str, args: dict[str, Any], user_text: str, turn: str = "") -> dict[str, Any]:
        """Run one tool of one part. `user_text` lets the part apply its own rules (a delete needs the person's own words); `turn` names this one question, so a change prepared in one turn cannot be confirmed in the same one. Never raises."""
        payload = json.dumps({"name": name, "args": args, "user_text": user_text, "turn": turn}).encode()
        try:
            status, body, _ = self._authed_full(module, "POST", module.tool, ASK_SECONDS, payload)
            raw = json.loads(body)
        except (OSError, http.client.HTTPException, ValueError):
            return {"ok": False, "error": f"{module.name} is not running"}
        if status != 200 or not isinstance(raw, dict):
            return {
                "ok": False,
                "error": str(raw.get("error", f"{module.name} could not do that"))[:300] if isinstance(raw, dict) else f"{module.name} could not do that",
            }
        items = [i for i in (self._item(module, x) for x in (raw.get("items") or [])[:24]) if i]
        notes = [str(n)[:300] for n in (raw.get("notes") or [])][:3]
        return {"ok": bool(raw.get("ok", True)), "data": raw.get("data"), "error": str(raw.get("error", ""))[:300], "items": items, "notes": notes}

    @staticmethod
    def _item(module: Module, item: Any) -> dict[str, str] | None:
        """One picture or document an app offers, checked: a picture must sit under the app's declared media path, a document needs a title."""
        if not isinstance(item, dict):
            return None
        kind = str(item.get("kind", ""))[:20]
        link = str(item.get("link", ""))[:300]
        if kind == "confirm" and item.get("title"):  # a change waiting for the person: a card that opens the part's confirmation window
            return {"kind": kind, "title": str(item["title"])[:200], "subtitle": str(item.get("subtitle", ""))[:200], "link": link}
        if kind == "document" and item.get("title"):
            return {
                "kind": kind,
                "title": str(item["title"])[:200],
                "subtitle": str(item.get("subtitle", ""))[:200],
                "text": str(item.get("text", ""))[:400],
                "link": link,
            }
        thumb = str(item.get("thumb", ""))
        if kind == "photo" and module.media and thumb.startswith(module.media) and ".." not in thumb:
            return {"kind": kind, "thumb": f"/_atlas/api/media/{module.id}{thumb}", "link": link}
        return None

    def media(self, module: Module, path: str) -> tuple[int, bytes, str]:
        """A picture from an app, fetched on the page's behalf (the app's token never reaches the page). Only the app's declared media path is allowed."""
        if not module.media or not path.startswith(module.media) or ".." in path or "?" in path:
            return 404, b"", ""
        try:
            return self._authed_full(module, "GET", path, SEARCH_SECONDS)
        except (OSError, http.client.HTTPException):
            return 502, b"", ""
