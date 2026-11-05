from __future__ import annotations

import http.client
import json
import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fake_app import FakeApp

from atlas.registry import load
from atlas.server import Atlas, make_handler
from atlas.upstream import Upstreams


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class Running:
    atlas: Atlas
    port: int
    apps: dict[str, FakeApp]

    def request(self, method: str, path: str, host: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers={"Host": host, **(headers or {})})
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def shell(self, path: str) -> tuple[int, dict[str, str], bytes]:
        return self.request("GET", path, f"atlas.localhost:{self.port}")

    def json(self, path: str) -> Any:
        return json.loads(self.shell(path)[2])


def manifest(mid: str, upstream: str, **extra: Any) -> dict[str, Any]:
    return {"id": mid, "name": mid.title(), "upstream": upstream, "pages": [{"id": "home", "label": "Home"}], **extra}


@pytest.fixture
def running(tmp_path: Path) -> Iterator[Running]:
    photos, money = FakeApp(token="secret"), FakeApp()
    money.require_header = "X-Fake"
    (tmp_path / "money.json").write_text(
        json.dumps(manifest("money", money.url, health="/api/health", scan="/api/scan", ask="/api/ask", keywords=["spent", "money"], headers={"X-Fake": "1"}))
    )
    (tmp_path / "photos.json").write_text(
        json.dumps(
            manifest(
                "photos",
                photos.url,
                search="/api/search",
                scan="/api/scan",
                ask="/api/ask",
                keywords=["photo", "picture"],
                media="/api/photo/",
                auth={"meta": "app-token", "header": "X-App-Token"},
            )
        )
    )
    port = free_port()
    modules = load(tmp_path)
    atlas = Atlas(modules, "atlas.localhost", port, Upstreams(modules), model_url=photos.url)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(atlas))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Running(atlas, port, {"photos": photos, "money": money})
    server.shutdown()
    server.server_close()
    photos.close()
    money.close()
