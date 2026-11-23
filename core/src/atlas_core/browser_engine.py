"""The real browser engine behind the `Browser` seam (Stage 6; TARGET_ARCHITECTURE 20): a local Playwright Chromium in its OWN process, with nothing of the Core's.

* **Isolated.** `WorkerBrowser` starts `python -m atlas_core.browser_worker` with a scrubbed environment (no Keychain item, key, token or home path of the Core), talks to it over a pipe in JSON lines, bounds every
  call with a timeout and kills the worker if it does not answer. The worker holds no Core state and no secret; a fresh, empty browser context is made for every worker and nothing is persisted (no profile, no
  cookies kept, no downloads).
* **Narrow.** Every request the page makes (the page itself, redirects, images, scripts, frames) is checked against the allowed hosts and schemes and aborted otherwise, so a page cannot pull in or send anything
  to a place the owner did not allow; a page that ends up off the allow-list is not read.
* **Data, not instructions.** The engine returns the visible text of a page; what the page says is the workflow's untrusted data and never an instruction (`browser.py`).

The owner's allowed hosts and the steps come from the caller; this module decides nothing about policy except refusing everything outside what it was given.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlsplit

CALL_TIMEOUT = 45.0
PAGE_TIMEOUT_MS = 20_000
MAX_TEXT = 200_000
MAX_REDIRECTS = 5
REDIRECTS = frozenset({301, 302, 303, 307, 308})
SAFE_ENV = (
    "PATH",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "PLAYWRIGHT_BROWSERS_PATH",
    "PYTHONPATH",
    "HOME",
)  # all the worker is told; nothing else of this process's environment reaches it


class BrowserBlocked(Exception):
    """A step the engine refused or could not do. Carries a code, never page content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def allowed(url: str, hosts: frozenset[str], schemes: frozenset[str]) -> bool:
    parts = urlsplit(url)
    return parts.scheme in schemes and (parts.hostname or "") in hosts


class PlaywrightBrowser:
    """The engine itself. Run inside the worker process, not in the Core."""

    def __init__(self, hosts: Iterable[str], schemes: Iterable[str] = ("https",), executable: str | None = None, no_sandbox: bool = False) -> None:
        from playwright.sync_api import sync_playwright

        self.hosts, self.schemes = frozenset(hosts), frozenset(schemes)
        self.blocked = 0
        self.final: str | None = None
        self._page: Any = None
        self._pw = sync_playwright().start()
        args = ["--no-sandbox"] if no_sandbox else []
        self._browser = self._pw.chromium.launch(headless=True, executable_path=executable, args=args)
        self._context = self._browser.new_context(accept_downloads=False, service_workers="block", permissions=[], java_script_enabled=True)
        self._context.route("**/*", self._gate)
        self._fresh_page()

    def _fresh_page(self) -> None:
        with contextlib.suppress(Exception):
            if getattr(self, "_page", None) is not None:
                self._page.close()
        self._page = self._context.new_page()
        self._page.set_default_timeout(PAGE_TIMEOUT_MS)

    def _gate(self, route: Any) -> None:
        """Every request is judged here, and every redirect hop is followed HERE (never by the browser, which would follow it unseen): each hop must be on the allow-list before anything is requested from it."""
        url = route.request.url
        try:
            for _hop in range(MAX_REDIRECTS + 1):
                if not allowed(url, self.hosts, self.schemes):
                    raise BrowserBlocked("destination_not_allowed")
                response = route.fetch(url=url, max_redirects=0)
                location = response.headers.get("location")
                if response.status in REDIRECTS and location:
                    url = urljoin(url, location)
                    continue
                if route.request.is_navigation_request() and route.request.frame == self._page.main_frame:
                    self.final = url  # where the page really ended up, after the hops that were allowed
                route.fulfill(response=response)
                return
            raise BrowserBlocked("too_many_redirects")
        except Exception:  # noqa: BLE001  (a refusal or a failure: the request is dropped, nothing is returned)
            self.blocked += 1
            route.abort()

    def open(self, url: str) -> tuple[str, str]:
        if not allowed(url, self.hosts, self.schemes):
            raise BrowserBlocked("destination_not_allowed")
        self.final = None
        try:
            self._page.goto(url)
        except Exception:  # noqa: BLE001  (a navigation that failed or was aborted by the gate: a code, never the text)
            self._fresh_page()  # a refused navigation leaves the page on the browser's error page: start from a clean one
            raise BrowserBlocked("navigation_failed") from None
        final = self.final or self._page.url
        if not allowed(final, self.hosts, self.schemes):
            raise BrowserBlocked("redirected_off_allow_list")
        return final, self._page.inner_text("body")[:MAX_TEXT]

    def fill(self, field_name: str, value: str) -> None:
        try:
            self._page.fill(f'[name="{_attr(field_name)}"]', value)
        except Exception:  # noqa: BLE001
            raise BrowserBlocked("no_such_field") from None

    def press(self, control: str) -> None:
        try:
            self._page.get_by_role("button", name=control).first.click()
        except Exception:  # noqa: BLE001
            raise BrowserBlocked("no_such_control") from None

    def close(self) -> None:
        for step in (self._context.close, self._browser.close, self._pw.stop):
            with contextlib.suppress(Exception):
                step()


def _attr(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum() or ch in "_-.")[:80]


class WorkerBrowser:
    """The `Browser` seam over a worker process. Calls are serialised; one that does not answer in time kills the worker and raises."""

    def __init__(self, hosts: Iterable[str], schemes: Iterable[str] = ("https",), *, no_sandbox: bool = False, executable: str | None = None) -> None:
        env = {k: os.environ[k] for k in SAFE_ENV if k in os.environ}
        config = json.dumps({"hosts": sorted(hosts), "schemes": sorted(schemes), "no_sandbox": no_sandbox, "executable": executable})
        self._proc = subprocess.Popen(
            [sys.executable, "-s", "-m", "atlas_core.browser_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            close_fds=True,
        )
        self._lock = threading.Lock()
        self._seq = 0
        assert self._proc.stdin is not None
        self._proc.stdin.write(config + "\n")
        self._proc.stdin.flush()
        self._call("ready")

    def _call(self, op: str, *args: str) -> Any:
        with self._lock:
            self._seq += 1
            assert self._proc.stdin is not None and self._proc.stdout is not None
            timer = threading.Timer(CALL_TIMEOUT, self._proc.kill)
            timer.start()
            try:
                self._proc.stdin.write(json.dumps({"id": self._seq, "op": op, "args": list(args)}) + "\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
            except (BrokenPipeError, ValueError, OSError):
                line = ""
            finally:
                timer.cancel()
        if not line:
            raise BrowserBlocked("worker_stopped")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise BrowserBlocked(str(reply.get("code", "worker_error")))
        return reply.get("result")

    def open(self, url: str) -> tuple[str, str]:
        final, text = self._call("open", url)
        return str(final), str(text)

    def fill(self, field_name: str, value: str) -> None:
        self._call("fill", field_name, value)

    def press(self, control: str) -> None:
        self._call("press", control)

    def close(self) -> None:
        with contextlib.suppress(BrowserBlocked):
            self._call("close")
        self._proc.kill()
        self._proc.wait()
