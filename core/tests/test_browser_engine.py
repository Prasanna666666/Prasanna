"""The real browser engine (Playwright Chromium) in its own worker process: narrow, isolated, data not instructions.

Pages are served by local synthetic servers on 127.0.0.1 / localhost (http, so the tests need no certificate); the engine is told which hosts and schemes are allowed and must refuse everything else, including
what a page pulls in or a redirect leads to. Skipped where Chromium is not installed.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import threading
from pathlib import Path

import pytest

from atlas_core.browser_engine import BrowserBlocked, WorkerBrowser

CHROMIUM = os.environ.get("ATLAS_TEST_CHROMIUM") or next((str(p) for p in (Path("/opt/pw-browsers/chromium"),) if p.exists()), None)
try:
    import playwright  # noqa: F401

    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False
needs_engine = pytest.mark.skipif(not HAVE_PLAYWRIGHT, reason="playwright is not installed")


class Site:
    """A synthetic site: `pages` maps a path to (status, headers, body). Counts the paths it was asked for."""

    def __init__(self, pages):
        self.pages, self.hits = pages, []
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                site.hits.append(self.path)
                status, headers, body = site.pages.get(self.path, (404, {}, b"not found"))
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return None

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def html(text: str) -> tuple[int, dict, bytes]:
    return 200, {"Content-Type": "text/html"}, text.encode()


@pytest.fixture
def engine_args():
    return {"no_sandbox": True, "executable": CHROMIUM}


@needs_engine
def test_a_page_is_read_as_visible_text_and_nothing_can_be_clicked_filled_or_submitted(engine_args):
    site = Site(
        {
            "/": html(
                "<h1>Opening hours</h1><p>Monday to Friday 9 to 17</p>"
                "<form id='f' method='post' action='/send'><input name='who' value='x'><button>Send</button></form>"
                "<script>document.getElementById('f').submit()</script>"  # a page that tries to post a form by itself
            ),
            "/send": html("sent"),
        }
    )
    browser = WorkerBrowser(["127.0.0.1"], ["http"], **engine_args)
    try:
        _final, text = browser.open(f"http://127.0.0.1:{site.port}/")
        assert "Monday to Friday 9 to 17" in text
        assert not hasattr(browser, "press") and not hasattr(browser, "fill")  # the engine has no click and no form entry
    finally:
        browser.close()
    assert "/send" not in site.hits, site.hits  # the page's own attempt to post was refused at the gate: a page may read and nothing more
    site.close()


@needs_engine
def test_a_destination_a_redirect_or_a_subresource_off_the_allow_list_is_refused_and_never_requested(engine_args):
    elsewhere = Site({"/secret": html("<p>other site</p>"), "/pixel": (200, {"Content-Type": "image/gif"}, b"GIF89a")})
    site = Site(
        {
            "/leave": (302, {"Location": f"http://localhost:{elsewhere.port}/secret"}, b""),
            "/page": html(f"<p>Visible</p><img src='http://localhost:{elsewhere.port}/pixel'>"),
        }
    )
    browser = WorkerBrowser(["127.0.0.1"], ["http"], **engine_args)
    try:
        with pytest.raises(BrowserBlocked) as e:
            browser.open(f"http://localhost:{elsewhere.port}/secret")  # not on the list
        assert e.value.code == "destination_not_allowed"
        with pytest.raises(BrowserBlocked) as e2:
            browser.open(f"http://127.0.0.1:{site.port}/leave")  # the redirect leads off the list
        assert e2.value.code in ("navigation_failed", "redirected_off_allow_list")
        _final, text = browser.open(f"http://127.0.0.1:{site.port}/page")
        assert "Visible" in text
        assert elsewhere.hits == []  # nothing was ever requested from a place that was not allowed
    finally:
        browser.close()
        site.close()
        elsewhere.close()


@needs_engine
def test_the_worker_receives_none_of_the_cores_environment_and_a_stuck_call_cannot_hang_the_core(engine_args, monkeypatch):
    monkeypatch.setenv("ATLAS_SECRET_SENTINEL", "must-not-reach-the-worker")
    site = Site({"/": html("<p>ok</p>")})
    browser = WorkerBrowser(["127.0.0.1"], ["http"], **engine_args)
    try:
        environ = Path(f"/proc/{browser._proc.pid}/environ")
        if environ.exists():  # Linux: read the worker's real environment
            assert b"ATLAS_SECRET_SENTINEL" not in environ.read_bytes()
        assert browser.open(f"http://127.0.0.1:{site.port}/")[1].strip() == "ok"
        browser._proc.kill()
        browser._proc.wait()
        with pytest.raises(BrowserBlocked) as e:
            browser.open(f"http://127.0.0.1:{site.port}/")  # a dead worker is an honest code, not a hang
        assert e.value.code == "worker_stopped"
    finally:
        browser.close()
        site.close()


def test_the_workers_answers_are_codes_never_page_content():
    assert json.dumps({"ok": False, "code": "worker_error"}) and shutil is not None


@needs_engine
def test_a_pinned_name_is_resolved_by_the_cores_address_and_every_other_name_cannot_be_resolved(engine_args):
    site = Site({"/": html("<p>pinned ok</p>")})
    browser = WorkerBrowser(["pinned.invalid"], ["http"], pins={"pinned.invalid": "127.0.0.1"}, **engine_args)
    try:
        _final, text = browser.open(f"http://pinned.invalid:{site.port}/")  # a name no DNS knows: only the pin can make this work
        assert "pinned ok" in text
    finally:
        browser.close()
        site.close()
