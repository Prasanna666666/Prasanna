import ast
import pathlib
import socket
import threading

import pytest
from kit import netguard

from orbit.modules import ALL, tools

SRC = pathlib.Path(__file__).parent.parent / "src" / "orbit"
NETWORK_MODULES = {"requests", "httpx", "aiohttp", "http.client", "ftplib", "smtplib", "imaplib", "poplib", "telnetlib", "websockets", "anthropic", "openai"}


@pytest.fixture
def guard():
    netguard.install()
    yield
    netguard.uninstall()


def test_blocks_all_dns_and_direct_ip(guard):
    for name in ("example.com", "api.open-meteo.com", "api.frankfurter.app"):
        with pytest.raises(netguard.EgressBlocked):
            socket.getaddrinfo(name, 443)
    s = socket.socket()
    with pytest.raises(netguard.EgressBlocked):
        s.connect(("93.184.216.34", 443))
    s.close()


def test_loopback_still_works(guard):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def accept_once():
        srv.accept()[0].close()

    threading.Thread(target=accept_once, daemon=True).start()
    socket.create_connection(("127.0.0.1", srv.getsockname()[1])).close()
    srv.close()


def test_no_internet_capable_tools():
    banned = {"weather", "exchange_rate", "network_log", "search_web", "fetch_url"}
    assert not banned & set(tools(ALL))


def test_no_network_libraries_imported_anywhere():
    """Build-time check: only llm.py (local Ollama over urllib) and library_client.py (the Documents service on this computer) may touch the network, and egress is guarded."""
    for f in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for n in names:
                assert n not in NETWORK_MODULES, f"{f.name} imports {n}"
                if n.startswith("urllib") and "request" in n:
                    assert f.name in ("llm.py", "library_client.py"), (
                        f"{f.name} uses urllib.request"
                    )  # the model, and the Documents service (both on this computer)


def test_the_model_server_can_only_be_on_this_computer_or_its_private_network():
    from kit import llm

    for ok in ("http://127.0.0.1:11434", "http://localhost:11434", "http://ollama.internal:11434", "http://192.168.1.20:11434", "http://[::1]:11434"):
        llm.OllamaClient(ok)
    for bad in (
        "http://example.com",
        "https://api.openai.com",
        "http://8.8.8.8:11434",
        "http://evil.internal.example.com",
        "file:///etc/passwd",
        "ftp://127.0.0.1",
    ):
        with pytest.raises(ValueError):
            llm.OllamaClient(bad)


def test_the_settings_page_cannot_point_the_assistant_at_the_internet(tmp_path, monkeypatch):
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from orbit import web

    monkeypatch.setenv("ORBIT_HOME", str(tmp_path))
    monkeypatch.delenv("ORBIT_DB_KEY", raising=False)
    from orbit import db
    from orbit.modules import ALL

    c = db.connect()
    db.migrate(c, ALL)
    c.close()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(web.State()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:

        def post(host):
            req = urllib.request.Request(
                f"http://127.0.0.1:{srv.server_address[1]}/api/settings",
                json.dumps({"ollama_host": host}).encode(),
                {"X-Orbit": "1", "Content-Type": "application/json"},
            )
            try:
                return urllib.request.urlopen(req).status
            except urllib.error.HTTPError as e:
                return e.code

        assert post("http://example.com:11434") == 400
        assert post("http://127.0.0.1:11434") == 200
    finally:
        srv.shutdown()
